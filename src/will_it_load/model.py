"""A behavioural model of LM Studio's model-loading guardrail.

Everything here is an independent re-implementation written for this project.
It contains no LM Studio code. The constants describe observed behaviour and are
checked against LM Studio's own ``lms load --estimate-only`` output (see
``data/measurements.json`` and ``docs/FINDINGS.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

KiB = 1024
MiB = 1024 * KiB
GiB = 1024 * MiB

#: Memory below this amount is counted with the first ratio, memory above it with the second.
LAYER_CUTOFF = 16 * GiB

#: mode -> (ratio for the first 16 GiB, ratio for everything above)
PROFILES = {
    "strict": (0.65, 0.85),
    "balanced": (0.75, 0.85),
    "relaxed": (0.85, 0.90),
}

#: Older settings files store the modes under different names.
LEGACY_MODE_NAMES = {"low": "strict", "medium": "balanced", "high": "relaxed"}

MODES = ("off", "strict", "balanced", "relaxed", "custom")

#: Extra memory a loaded model holds beyond its file size (measured: gpt-oss-20b MLX, 32k context, idle:
#: counted as 11.85 GiB for an 11.27 GiB file). With no model loaded, nothing counts.
LOADED_MODEL_OVERHEAD = 0.58 * GiB

#: Multiplier LM Studio applies to the file size when it has no detailed estimator
#: for a model (observed for MLX/safetensors models and embedding models).
FLAT_ESTIMATE_FACTOR = 1.4


def normalize_mode(mode: str) -> str:
    mode = mode.strip().lower()
    mode = LEGACY_MODE_NAMES.get(mode, mode)
    if mode not in MODES:
        raise ValueError(f"unknown guardrail mode {mode!r}; expected one of {', '.join(MODES)}")
    return mode


def layered(total: float, low_ratio: float, high_ratio: float, cutoff: float = LAYER_CUTOFF) -> float:
    """Usable bytes: ``low_ratio`` of the first ``cutoff`` bytes plus ``high_ratio`` of the rest."""
    if total < 0:
        raise ValueError("total memory must not be negative")
    return min(total, cutoff) * low_ratio + max(0.0, total - cutoff) * high_ratio


def counted_memory(ram_bytes: int, vram_bytes: int = 0, platform: str = "darwin") -> int:
    """Memory the guardrail budgets against.

    On macOS (unified memory) only RAM counts. On Windows/Linux, dedicated VRAM is added.
    """
    return ram_bytes if platform == "darwin" else ram_bytes + vram_bytes


def limit_bytes(mode: str, total_bytes: float, custom_threshold_bytes: int = 0) -> float:
    """The guardrail budget for a mode. ``float('inf')`` when guardrails are off."""
    mode = normalize_mode(mode)
    if mode == "off":
        return float("inf")
    if mode == "custom":
        return float(custom_threshold_bytes)
    return layered(total_bytes, *PROFILES[mode])


def in_use_bytes(loaded_sizes) -> float:
    """Approximate memory LM Studio counts for models that are loaded right now."""
    sizes = list(loaded_sizes)
    return float(sum(sizes)) + LOADED_MODEL_OVERHEAD * len(sizes)


def estimate_bytes(size_bytes: int, fmt: str = "safetensors", kind: str = "llm") -> Optional[float]:
    """LM Studio's loaded-size estimate for a model.

    Returns ``None`` for GGUF LLMs: LM Studio computes those from context length,
    layers, KV-cache type and offload, which this project does not model yet. Use
    ``lms load <key> --estimate-only`` for them (``will-it-load verify`` does that).
    """
    if fmt.lower() == "gguf" and kind.lower() in ("llm", "vlm"):
        return None
    return size_bytes * FLAT_ESTIMATE_FACTOR


@dataclass(frozen=True)
class Verdict:
    estimate_bytes: Optional[float]
    in_use_bytes: float
    limit_bytes: float

    @property
    def known(self) -> bool:
        return self.estimate_bytes is not None

    @property
    def will_load(self) -> Optional[bool]:
        if self.estimate_bytes is None:
            return None
        return self.in_use_bytes + self.estimate_bytes <= self.limit_bytes

    @property
    def headroom_bytes(self) -> Optional[float]:
        if self.estimate_bytes is None:
            return None
        return self.limit_bytes - self.in_use_bytes - self.estimate_bytes


def decide(estimate: Optional[float], in_use_bytes: float, limit: float) -> Verdict:
    """``in_use_bytes`` is memory held by LM Studio's own (not-unloading) model processes."""
    return Verdict(estimate, in_use_bytes, limit)


def fmt_bytes(n: Optional[float]) -> str:
    if n is None:
        return "?"
    if n == float("inf"):
        return "unlimited"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= GiB:
        return f"{sign}{n / GiB:.2f} GiB"
    return f"{sign}{n / MiB:.2f} MiB"


def parse_size(text: str, binary: bool = False) -> int:
    """Parse ``"12.1GB"``, ``"11.3 GiB"``, ``"512MB"`` or plain bytes.

    GB/MB are decimal (10^9), matching the model sizes LM Studio shows (``lms ps``: "12.10 GB").
    GiB/MiB are binary. With ``binary=True`` (used for RAM/VRAM, where "32 GB" means 32 GiB)
    GB/MB are read as GiB/MiB too.
    """
    t = text.strip().replace(" ", "").lower()
    g, m, k = (GiB, MiB, KiB) if binary else (10 ** 9, 10 ** 6, 10 ** 3)
    units = [("gib", GiB), ("gb", g), ("g", g), ("mib", MiB), ("mb", m), ("m", m), ("kib", KiB), ("kb", k), ("b", 1)]
    for suffix, mult in units:
        if t.endswith(suffix):
            return int(float(t[: -len(suffix)]) * mult)
    return int(float(t))
