import json
from pathlib import Path

import pytest

from will_it_load.cli import main
from will_it_load.model import (
    GiB,
    MiB,
    counted_memory,
    decide,
    estimate_bytes,
    in_use_bytes,
    limit_bytes,
    normalize_mode,
    parse_size,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "measurements.json"


@pytest.mark.parametrize(
    "mode,ram_gib,expected_gib",
    [
        ("balanced", 32, 25.6),
        ("strict", 32, 24.0),
        ("relaxed", 32, 28.0),
        ("balanced", 16, 12.0),
        ("balanced", 8, 6.0),
        ("balanced", 64, 52.8),
        ("relaxed", 128, 114.4),
    ],
)
def test_limits(mode, ram_gib, expected_gib):
    assert limit_bytes(mode, ram_gib * GiB) / GiB == pytest.approx(expected_gib)


def test_legacy_mode_names():
    assert normalize_mode("medium") == "balanced"
    assert normalize_mode("low") == "strict"
    assert normalize_mode("high") == "relaxed"
    with pytest.raises(ValueError):
        normalize_mode("ludicrous")


def test_off_and_custom():
    assert limit_bytes("off", 8 * GiB) == float("inf")
    assert limit_bytes("custom", 8 * GiB, 20 * GiB) == 20 * GiB


def test_counted_memory_platforms():
    assert counted_memory(32 * GiB, 12 * GiB, "darwin") == 32 * GiB
    assert counted_memory(32 * GiB, 12 * GiB, "win32") == 44 * GiB
    assert counted_memory(32 * GiB, 12 * GiB, "linux") == 44 * GiB


def test_estimates():
    assert estimate_bytes(10 * GiB, "safetensors", "llm") == pytest.approx(14 * GiB)
    assert estimate_bytes(84106624, "gguf", "embedding") / MiB == pytest.approx(112.29, abs=0.01)
    assert estimate_bytes(10 * GiB, "gguf", "llm") is None


def test_decide():
    v = decide(19.74 * GiB, 11.57 * GiB, 25.6 * GiB)
    assert v.will_load is False and v.headroom_bytes < 0
    assert decide(None, 0, 1).will_load is None


def test_parse_size():
    assert parse_size("12.1GB") == 12_100_000_000
    assert parse_size("32GB", binary=True) == 32 * GiB
    assert parse_size("12.5 GiB") == int(12.5 * GiB)
    assert parse_size("512MiB") == 512 * MiB
    assert parse_size("1024") == 1024


def _rows():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for report in data["reports"]:
        for row in report["rows"]:
            yield report, row


@pytest.mark.parametrize("report,row", list(_rows()))
def test_measurements_replay(report, row):
    """Every recorded `lms load --estimate-only` result must be reproduced by the model."""
    est = estimate_bytes(row["size_bytes"], row["format"], row["type"])
    if row["lms_estimate_bytes"] is not None and est is not None:
        assert abs(est - row["lms_estimate_bytes"]) <= 0.006 * GiB
    m = report["machine"]
    limit = limit_bytes(report["guardrail_mode"], counted_memory(m["ram_bytes"], m["vram_bytes"], m["platform"]))
    sizes = {r["model"]: r["size_bytes"] for _, r in _rows()}
    in_use = in_use_bytes(sizes[k] for k in report["loaded_models"])
    verdict = decide(est, in_use, limit).will_load
    if row["lms_will_load"] is not None and verdict is not None:
        assert verdict == row["lms_will_load"]


def test_cli_check(capsys):
    code = main(["check", "14.1GB", "--in-use", "12.1GB", "--mode", "balanced", "--ram", "32GB", "--platform", "darwin", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and out["will_load"] is False
    code = main(["check", "14.1GB", "--mode", "balanced", "--ram", "32GB", "--platform", "darwin", "--json"])
    assert code == 0


def test_cli_limits(capsys):
    assert main(["limits", "--mode", "balanced", "--ram", "32GB", "--platform", "darwin"]) == 0
    assert "25.60 GiB" in capsys.readouterr().out


def _probes():
    return json.loads(DATA.read_text(encoding="utf-8")).get("probes", [])


@pytest.mark.parametrize("probe", _probes(), ids=lambda p: p["scenario"][:30])
def test_probe_boundaries(probe):
    """Measured flip point (largest accepted estimate) must match budget - in-use within 0.05 GiB."""
    m = probe["machine"]
    limit = limit_bytes(probe["guardrail_mode"], counted_memory(m["ram_bytes"], m["vram_bytes"], m["platform"]))
    predicted = limit - in_use_bytes(probe["loaded_model_sizes"].values())
    assert probe["found"]
    assert abs(probe["max_accepted_estimate_bytes"] - predicted) <= 0.05 * GiB
