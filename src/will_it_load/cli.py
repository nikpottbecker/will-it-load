"""Command line interface: ``will-it-load``."""

from __future__ import annotations

import argparse
import json
import platform as _platform
import sys
from typing import List, Optional

from . import __version__
from .environment import (
    ModelInfo,
    cpu_name,
    downloaded_models,
    lms_estimate,
    lms_path,
    loaded_models,
    read_guardrail_settings,
    read_jit_settings,
    system_platform,
    total_ram_bytes,
)
from .model import (
    GiB,
    MODES,
    PROFILES,
    counted_memory,
    decide,
    estimate_bytes,
    fmt_bytes,
    in_use_bytes,
    limit_bytes,
    normalize_mode,
    parse_size,
)


USE_COLOR = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def yes(text: str) -> str:
    return c(text, "32")


def no(text: str) -> str:
    return c(text, "31")


def dim(text: str) -> str:
    return c(text, "2")


def _machine(args) -> dict:
    plat = args.platform or system_platform()
    ram = parse_size(args.ram, binary=True) if args.ram else total_ram_bytes()
    vram = parse_size(args.vram, binary=True) if args.vram else 0
    g = read_guardrail_settings()
    mode = normalize_mode(args.mode or g.get("mode", "balanced"))
    custom = parse_size(args.custom, binary=True) if getattr(args, "custom", None) else int(g.get("customThresholdBytes", 0))
    total = counted_memory(ram, vram, plat)
    return {
        "platform": plat,
        "ram": ram,
        "vram": vram,
        "mode": mode,
        "custom": custom,
        "limit": limit_bytes(mode, total, custom),
        "settings_source": g.get("source"),
    }


def _add_machine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", help=f"guardrail mode ({', '.join(MODES)}); default: read from LM Studio settings")
    p.add_argument("--ram", help="total RAM, e.g. 32GB (default: this machine)")
    p.add_argument("--vram", help="dedicated VRAM, e.g. 12GB (Windows/Linux only; ignored on macOS)")
    p.add_argument("--platform", choices=["darwin", "win32", "linux"], help="default: this machine")
    p.add_argument("--custom", help="threshold for --mode custom, e.g. 20GB")


def _verdict_text(v) -> str:
    if v.will_load is None:
        return dim("unknown (GGUF LLM - run `will-it-load verify`)")
    return yes("LOADS") if v.will_load else no("BLOCKED")


def cmd_scan(args) -> int:
    m = _machine(args)
    models = downloaded_models()
    loaded = [] if args.assume_empty else loaded_models()
    in_use = in_use_bytes(x.size_bytes for x in loaded)
    print(f"LM Studio guardrail: {c(m['mode'], '1')}  |  budget {fmt_bytes(m['limit'])}"
          f"  |  RAM {fmt_bytes(m['ram'])} ({m['platform']})")
    if loaded:
        print(f"Currently loaded: {', '.join(x.key for x in loaded)}  ->  ~{fmt_bytes(in_use)} in use")
        jit = read_jit_settings()
        manual = [x.key for x in loaded if x.ttl_ms is None]
        if manual and jit["unloadPreviousJITModelOnLoad"]:
            print(c("  note: ", "33") + f"{', '.join(manual)} looks manually loaded (no TTL). Just-in-time loads only "
                  "evict other JIT models, so this one stays and counts against the budget. "
                  "Run `lms unload --all` first.")
    else:
        print(dim("No model loaded."))
    if not models:
        print("No downloaded models found (is LM Studio installed? is `lms` on PATH?).")
        return 1
    print()
    width = max(len(x.key) for x in models)
    print(f"{'model':{width}}  {'file':>10}  {'estimate':>10}  {'now':<9}  alone")
    for x in models:
        est = estimate_bytes(x.size_bytes, x.fmt, x.kind)
        now = decide(est, in_use, m["limit"])
        alone = decide(est, 0, m["limit"])
        print(f"{x.key:{width}}  {fmt_bytes(x.size_bytes):>10}  {fmt_bytes(est):>10}  "
              f"{_verdict_text(now):<9}  {_verdict_text(alone)}")
    print(dim("\nestimate = file size x 1.4 for MLX/safetensors and embedding models; "
              "'now' counts models that are loaded right now."))
    return 0


def cmd_check(args) -> int:
    m = _machine(args)
    size = parse_size(args.size)
    est = estimate_bytes(size, args.format, args.kind)
    in_use = in_use_bytes([parse_size(args.in_use)] * 1) if args.in_use else 0.0
    v = decide(est, in_use, m["limit"])
    if args.json:
        print(json.dumps({"mode": m["mode"], "limit_bytes": m["limit"], "estimate_bytes": est,
                          "in_use_bytes": in_use, "will_load": v.will_load, "headroom_bytes": v.headroom_bytes}))
        return 0 if v.will_load is not False else 2
    print(f"mode {m['mode']}, budget {fmt_bytes(m['limit'])}, in use {fmt_bytes(in_use)}")
    print(f"model {fmt_bytes(size)} ({args.format}) -> estimate {fmt_bytes(est)} -> {_verdict_text(v)}"
          + (f"  (headroom {fmt_bytes(v.headroom_bytes)})" if v.known else ""))
    return 0 if v.will_load is not False else 2


def cmd_limits(args) -> int:
    m = _machine(args)
    total = counted_memory(m["ram"], m["vram"], m["platform"])
    print(f"Counted memory: {fmt_bytes(total)} ({m['platform']}: "
          f"{'RAM only' if m['platform'] == 'darwin' else 'RAM + VRAM'})")
    for mode in ("strict", "balanced", "relaxed"):
        lo, hi = PROFILES[mode]
        mark = "  <- current" if mode == m["mode"] else ""
        print(f"  {mode:<9} {int(lo * 100)}% of first 16 GiB + {int(hi * 100)}% of the rest = "
              f"{fmt_bytes(limit_bytes(mode, total))}{mark}")
    print(f"  custom    fixed threshold = {fmt_bytes(m['custom'])}{'  <- current' if m['mode'] == 'custom' else ''}")
    print(f"  off       no limit{'  <- current' if m['mode'] == 'off' else ''}")
    return 0


def cmd_verify(args) -> int:
    """Compare this model's predictions with LM Studio's own `lms load --estimate-only`."""
    if not lms_path():
        print("`lms` CLI not found. Install it from LM Studio (Developer tab) and retry.")
        return 1
    m = _machine(args)
    loaded = loaded_models()
    in_use = in_use_bytes(x.size_bytes for x in loaded)
    rows = []
    models: List[ModelInfo] = downloaded_models()
    if args.models:
        models = [x for x in models if x.key in args.models]
    for x in models:
        est = estimate_bytes(x.size_bytes, x.fmt, x.kind)
        ours = decide(est, in_use, m["limit"])
        theirs = lms_estimate(x.key) or {}
        est_match: Optional[bool] = None
        if est is not None and theirs.get("total_bytes"):
            # lms prints two decimals; allow rounding error
            est_match = abs(est - theirs["total_bytes"]) <= max(0.006 * GiB, 0.001 * est)
        verdict_match = None if ours.will_load is None or theirs.get("will_load") is None \
            else ours.will_load == theirs["will_load"]
        rows.append({
            "model": x.key, "format": x.fmt, "type": x.kind, "size_bytes": x.size_bytes,
            "predicted_estimate_bytes": est, "lms_estimate_bytes": theirs.get("total_bytes"),
            "lms_confidence": theirs.get("confidence"),
            "predicted_will_load": ours.will_load, "lms_will_load": theirs.get("will_load"),
            "estimate_match": est_match, "verdict_match": verdict_match,
        })
    report = {
        "tool": f"will-it-load {__version__}",
        "machine": {"platform": m["platform"], "cpu": cpu_name(), "ram_bytes": m["ram"], "vram_bytes": m["vram"],
                    "os": _platform.platform(terse=True)},
        "guardrail_mode": m["mode"], "predicted_limit_bytes": m["limit"],
        "loaded_models": [x.key for x in loaded], "rows": rows,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for r in rows:
            ok = {True: yes("match"), False: no("MISMATCH"), None: dim("n/a")}
            print(f"{r['model']}: ours {fmt_bytes(r['predicted_estimate_bytes'])} vs lms "
                  f"{fmt_bytes(r['lms_estimate_bytes'])} -> {ok[r['estimate_match']]}; verdict {ok[r['verdict_match']]}")
        print(dim("\nShare the result: `will-it-load verify --json` and paste it into a 'Measurement report' issue."))
    bad = [r for r in rows if r["estimate_match"] is False or r["verdict_match"] is False]
    return 3 if bad else 0


def cmd_probe(args) -> int:
    """Measure the real budget with a placeholder model (black-box, never loads anything)."""
    from . import probe

    if not lms_path():
        print("`lms` CLI not found. Install it from LM Studio (Developer tab) and retry.")
        return 1
    m = _machine(args)
    loaded = loaded_models()
    in_use = in_use_bytes(x.size_bytes for x in loaded)
    predicted = m["limit"] - in_use
    if predicted == float("inf"):
        print("Guardrails are off, nothing to measure.")
        return 0
    say = (lambda *a, **k: None) if args.json else print
    say(f"Predicted largest accepted estimate: {fmt_bytes(predicted)} "
        f"(budget {fmt_bytes(m['limit'])} - in use {fmt_bytes(in_use)})")
    say(f"This creates a placeholder model in {probe.probe_dir()} (sparse file, never loaded), asks "
          "`lms load --estimate-only` ~16 times and deletes the placeholder afterwards.")
    if not args.yes:
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            return 1
    lo, hi = predicted * (1 - args.span), predicted * (1 + args.span)
    try:
        r = probe.bisect_boundary(lo, hi, steps=args.steps, log=say)
    except RuntimeError as e:
        print(no(str(e)))
        return 1
    report = {
        "tool": f"will-it-load {__version__}", "experiment": "E1 probe",
        "machine": {"platform": m["platform"], "cpu": cpu_name(), "ram_bytes": m["ram"], "vram_bytes": m["vram"],
                    "os": _platform.platform(terse=True)},
        "guardrail_mode": m["mode"], "loaded_models": [x.key for x in loaded],
        "predicted_limit_bytes": m["limit"], "predicted_in_use_bytes": in_use,
        "predicted_max_estimate_bytes": predicted, **r,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    elif r.get("found"):
        got = r["max_accepted_estimate_bytes"]
        diff = got - predicted
        print(f"Measured largest accepted estimate: {fmt_bytes(got)}  (prediction off by {fmt_bytes(diff)})")
        print(dim("Post `will-it-load probe --json --yes` in a measurement issue to improve the model."))
    else:
        print(no(f"Boundary not inside {fmt_bytes(lo)}..{fmt_bytes(hi)}; retry with a larger --span. Details: {r}"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="will-it-load",
        description="Predict whether LM Studio's model-loading guardrail will let a model load (unofficial).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="check every downloaded model (default)")
    _add_machine_args(s)
    s.add_argument("--assume-empty", action="store_true", help="ignore currently loaded models")
    s.set_defaults(func=cmd_scan)

    k = sub.add_parser("check", help="check a model size without LM Studio")
    k.add_argument("size", help="model file size as LM Studio shows it, e.g. 15.1GB (decimal) or 14.1GiB")
    k.add_argument("--format", default="safetensors", help="safetensors (MLX) or gguf")
    k.add_argument("--kind", default="llm", help="llm, vlm or embedding")
    k.add_argument("--in-use", help="size of models that stay loaded, e.g. 12.1GB (as in `lms ps`)")
    k.add_argument("--json", action="store_true")
    _add_machine_args(k)
    k.set_defaults(func=cmd_check)

    li = sub.add_parser("limits", help="show the budget of every guardrail mode on this machine")
    _add_machine_args(li)
    li.set_defaults(func=cmd_limits)

    v = sub.add_parser("verify", help="compare predictions with `lms load --estimate-only` (does not load models)")
    v.add_argument("models", nargs="*", help="model keys (default: all)")
    v.add_argument("--json", action="store_true", help="machine-readable report for a measurement issue")
    _add_machine_args(v)
    v.set_defaults(func=cmd_verify)
    pr = sub.add_parser("probe", help="measure the real budget with a placeholder model (never loads anything)")
    pr.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--span", type=float, default=0.15, help="search +-this fraction around the prediction")
    pr.add_argument("--steps", type=int, default=14)
    _add_machine_args(pr)
    pr.set_defaults(func=cmd_probe)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("--") and argv[0] not in ("--help", "-h", "--version"):
        argv = ["scan", *argv]
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["scan", *argv])
    try:
        return args.func(args)
    except ValueError as e:
        parser.error(str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
