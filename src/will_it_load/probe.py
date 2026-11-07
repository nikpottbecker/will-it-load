"""Black-box measurement of the guardrail budget with a dummy model.

Creates a placeholder MLX model of a chosen size in LM Studio's models folder (a sparse file:
it takes almost no disk space on macOS/Linux), asks ``lms load --estimate-only`` whether it
would load, and bisects the size until the verdict flips. The model is never loaded. The
placeholder folder is deleted afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import time
from pathlib import Path
from typing import Callable, Optional

from .environment import downloaded_models, lmstudio_home, lms_estimate, system_platform
from .model import FLAT_ESTIMATE_FACTOR, GiB

PROBE_PUBLISHER = "will-it-load-probe"
PROBE_KEY = "probe-mlx"

MINIMAL_CONFIG = {
    "architectures": ["LlamaForCausalLM"],
    "model_type": "llama",
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "intermediate_size": 14336,
    "vocab_size": 32000,
    "max_position_embeddings": 8192,
}


def probe_dir() -> Path:
    return lmstudio_home() / "models" / PROBE_PUBLISHER / PROBE_KEY


def _weights(d: Path) -> Path:
    return d / "model.safetensors"


def create_probe(size_bytes: int) -> Path:
    d = probe_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(MINIMAL_CONFIG), encoding="utf-8")
    header = json.dumps({"__metadata__": {"format": "mlx", "created_by": "will-it-load probe"}}).encode()
    header += b" " * ((8 - len(header) % 8) % 8)
    with open(_weights(d), "wb") as f:
        f.write(struct.pack("<Q", len(header)))
        f.write(header)
    resize_probe(size_bytes)
    return d


def resize_probe(total_bytes: int) -> None:
    d = probe_dir()
    other = sum(p.stat().st_size for p in d.iterdir() if p.is_file() and p.name != "model.safetensors")
    os.truncate(_weights(d), max(64, int(total_bytes - other)))


def indexed_size() -> Optional[int]:
    for m in downloaded_models():
        if m.key == PROBE_KEY:
            return m.size_bytes
    return None


def wait_until_indexed(total_bytes: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if indexed_size() == int(total_bytes):
            return True
        time.sleep(1.0)
    return False


def remove_probe() -> None:
    root = lmstudio_home() / "models" / PROBE_PUBLISHER
    if root.exists():
        shutil.rmtree(root)


def bisect_boundary(lo_estimate: float, hi_estimate: float, steps: int = 14,
                    log: Callable[[str], None] = print) -> dict:
    """Find the largest estimate LM Studio still accepts. Bounds are *estimates* (file size x 1.4)."""
    if system_platform() == "win32":
        need = hi_estimate / FLAT_ESTIMATE_FACTOR * 1.1
        free = shutil.disk_usage(lmstudio_home()).free
        if free < need:
            raise RuntimeError(f"Windows may reserve the full placeholder size; need {need / GiB:.1f} GiB free disk.")

    def verdict(estimate: float) -> Optional[bool]:
        size = int(estimate / FLAT_ESTIMATE_FACTOR)
        resize_probe(size)
        if not wait_until_indexed(size):
            raise RuntimeError("LM Studio did not pick up the placeholder model (is LM Studio running?)")
        r = lms_estimate(PROBE_KEY) or {}
        return r.get("will_load")

    create_probe(int(lo_estimate / FLAT_ESTIMATE_FACTOR))
    try:
        if not wait_until_indexed(int(lo_estimate / FLAT_ESTIMATE_FACTOR)):
            raise RuntimeError("LM Studio did not index the placeholder model (is LM Studio running?)")
        lo_ok, hi_ok = verdict(lo_estimate), verdict(hi_estimate)
        log(f"  {lo_estimate / GiB:.2f} GiB -> {'loads' if lo_ok else 'blocked'};"
            f" {hi_estimate / GiB:.2f} GiB -> {'loads' if hi_ok else 'blocked'}")
        if not (lo_ok is True and hi_ok is False):
            return {"found": False, "lo_ok": lo_ok, "hi_ok": hi_ok}
        lo, hi = lo_estimate, hi_estimate
        for _ in range(steps):
            mid = (lo + hi) / 2
            if verdict(mid):
                lo = mid
            else:
                hi = mid
        return {"found": True, "max_accepted_estimate_bytes": lo, "min_rejected_estimate_bytes": hi}
    finally:
        remove_probe()
