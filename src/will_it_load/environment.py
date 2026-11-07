"""Read the local machine and LM Studio state (read-only; never changes settings)."""

from __future__ import annotations

import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .model import GiB


@dataclass
class ModelInfo:
    key: str
    size_bytes: int
    fmt: str
    kind: str
    ttl_ms: Optional[int] = None  # only for loaded models; JIT loads usually carry a TTL


def lmstudio_home() -> Path:
    return Path(os.environ.get("LMSTUDIO_HOME", Path.home() / ".lmstudio"))


def read_guardrail_settings(home: Optional[Path] = None) -> dict:
    path = (home or lmstudio_home()) / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": "balanced", "customThresholdBytes": 0, "source": "default (settings.json not found)"}
    g = dict(data.get("modelLoadingGuardrails") or {"mode": "balanced", "customThresholdBytes": 0})
    g["source"] = str(path)
    return g


def read_jit_settings(home: Optional[Path] = None) -> dict:
    path = (home or lmstudio_home()) / "settings.json"
    try:
        dev = json.loads(path.read_text(encoding="utf-8")).get("developer", {})
    except (OSError, ValueError):
        dev = {}
    return {
        "unloadPreviousJITModelOnLoad": dev.get("unloadPreviousJITModelOnLoad", True),
        "jitModelTTL": dev.get("jitModelTTL", {"enabled": True, "ttlSeconds": 3600}),
    }


def system_platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return "linux"


def total_ram_bytes() -> int:
    plat = system_platform()
    if plat == "darwin":
        return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
    if plat == "linux":
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    if plat == "win32":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    raise RuntimeError("cannot determine RAM; pass --ram")


def cpu_name() -> str:
    if system_platform() == "darwin":
        try:
            return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return _platform.processor() or _platform.machine()


def lms_path() -> Optional[str]:
    found = shutil.which("lms")
    if found:
        return found
    candidate = lmstudio_home() / "bin" / ("lms.exe" if system_platform() == "win32" else "lms")
    return str(candidate) if candidate.exists() else None


def _lms_json(*args: str) -> Optional[list]:
    exe = lms_path()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *args, "--json"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def _to_info(m: dict) -> ModelInfo:
    return ModelInfo(
        key=m.get("modelKey") or m.get("identifier") or m.get("path", "?"),
        size_bytes=int(m.get("sizeBytes") or 0),
        fmt=str(m.get("format") or "safetensors"),
        kind=str(m.get("type") or "llm"),
        ttl_ms=m.get("ttlMs"),
    )


def downloaded_models() -> List[ModelInfo]:
    data = _lms_json("ls")
    if data is not None:
        return [_to_info(m) for m in data]
    return _scan_model_dir(lmstudio_home() / "models")


def loaded_models() -> List[ModelInfo]:
    data = _lms_json("ps")
    return [_to_info(m) for m in data] if data else []


def _scan_model_dir(root: Path) -> List[ModelInfo]:
    """Fallback without the lms CLI: publisher/repo folders (MLX) and single .gguf files."""
    models: List[ModelInfo] = []
    if not root.is_dir():
        return models
    for publisher in sorted(p for p in root.iterdir() if p.is_dir()):
        for repo in sorted(p for p in publisher.iterdir() if p.is_dir()):
            ggufs = sorted(repo.glob("*.gguf"))
            if ggufs:
                for g in ggufs:
                    kind = "embedding" if re.search(r"embed", g.name, re.I) else "llm"
                    models.append(ModelInfo(f"{publisher.name}/{repo.name}/{g.name}", g.stat().st_size, "gguf", kind))
            else:
                size = sum(f.stat().st_size for f in repo.rglob("*") if f.is_file())
                models.append(ModelInfo(f"{publisher.name}/{repo.name}", size, "safetensors", "llm"))
    return models


def lms_estimate(key: str) -> Optional[dict]:
    """Run LM Studio's own dry run. Does not load the model."""
    exe = lms_path()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "load", key, "--estimate-only", "-y"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = out.stdout + out.stderr
    total = re.search(r"Estimated Total Memory:\s*([\d.]+)\s*(GiB|MiB|KiB|B)", text)
    if not total:
        return {"raw": text.strip(), "total_bytes": None, "will_load": None}
    value = float(total.group(1)) * {"GiB": GiB, "MiB": 1024 ** 2, "KiB": 1024, "B": 1}[total.group(2)]
    if "will fail to load" in text:
        verdict = False
    elif "may be loaded" in text:
        verdict = True
    else:
        verdict = None
    conf = re.search(r"Confidence:\s*(\w+)", text)
    return {"total_bytes": value, "will_load": verdict, "confidence": conf.group(1) if conf else None, "raw": text.strip()}
