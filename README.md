# Will it load? 🧮

**Find out why LM Studio says "insufficient system resources" and whether your next model will load.**

[![CI](https://github.com/nikpottbecker/will-it-load/actions/workflows/ci.yml/badge.svg)](https://github.com/nikpottbecker/will-it-load/actions/workflows/ci.yml)
[![Web calculator](https://img.shields.io/badge/try%20it-in%20your%20browser-4b5bdc)](https://nikpottbecker.github.io/will-it-load/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
![Unofficial](https://img.shields.io/badge/LM%20Studio-unofficial%20community%20tool-lightgrey)

> Unofficial community project. Not affiliated with or endorsed by LM Studio / Element Labs.
> See [LEGAL.md](LEGAL.md).

LM Studio has a safety feature called **model loading guardrails**. It stops you from loading a model that would freeze
your computer. That's useful, but when it says no, it doesn't tell you *why*. You may have 32 GB of RAM and a 12 GB
model, and it still refuses.

`will-it-load` shows you the numbers LM Studio uses: your **budget**, the model's **estimate** and what's **already
taken**. Every prediction is checked against LM Studio's own dry run (`lms load --estimate-only`).

```text
$ will-it-load
LM Studio guardrail: balanced  |  budget 25.60 GiB  |  RAM 32.00 GiB (darwin)
Currently loaded: gpt-oss-20b  ->  ~11.85 GiB in use
  note: gpt-oss-20b looks manually loaded (no TTL). Just-in-time loads only evict other JIT models,
        so this one stays and counts against the budget. Run `lms unload --all` first.

model                                       file    estimate  now        alone
devstral-small-2-24b-instruct-2512     14.10 GiB   19.74 GiB  BLOCKED    LOADS
gemma-4-26b-a4b-it-qat-mlx             14.57 GiB   20.39 GiB  BLOCKED    LOADS
gpt-oss-20b                            11.27 GiB   15.78 GiB  BLOCKED    LOADS
text-embedding-nomic-embed-text-v1.5   80.21 MiB  112.29 MiB  LOADS      LOADS
```

## The three facts that explain most "insufficient resources" errors

1. **Your budget is smaller than your RAM.** In Balanced mode you get 75 % of the first 16 GiB plus 85 % of the rest.
   On a 32 GB Mac that's **25.6 GiB**. Strict: 24.0 GiB. Relaxed: 28.0 GiB.
2. **MLX models are estimated at file size × 1.4**, no matter which context length you choose. A 14 GB model counts as
   about 20 GB.
3. **Just-in-time loading only swaps out other just-in-time models.** If you loaded a model with `lms load` or in the
   app, it stays loaded and blocks the next API request for a different model.

More detail, the exact rules and how sure we are about each one: [docs/FINDINGS.md](docs/FINDINGS.md).

## Try it

**In the browser, no install:** <https://nikpottbecker.github.io/will-it-load/>

**On your machine** (Python ≥ 3.9, no dependencies, reads LM Studio's state and never changes it):

```bash
uvx --from git+https://github.com/nikpottbecker/will-it-load will-it-load
```

or `pipx install git+https://github.com/nikpottbecker/will-it-load`, then:

| Command | What it does |
|---|---|
| `will-it-load` | Check every downloaded model against the current guardrail and the models loaded right now |
| `will-it-load limits` | Show the budget of every guardrail mode on this machine |
| `will-it-load check 15.1GB --in-use 12.1GB` | Check a size without LM Studio running (sizes as LM Studio shows them) |
| `will-it-load verify` | Compare every prediction with `lms load --estimate-only` (doesn't load anything) |
| `will-it-load verify --json` | Same, as a report you can paste into a [measurement issue](../../issues/new?template=measurement.yml) |
| `will-it-load probe` | Measure your real budget with a placeholder model (sparse file, never loaded, deleted afterwards) |

Options: `--mode strict|balanced|relaxed|custom|off`, `--ram 64GB`, `--vram 12GB --platform win32`, `--custom 20GB`.

## Fixes, in order of effort

1. `lms unload --all`, then let the API load the model just-in-time.
2. Pick a smaller quant: 4-bit instead of 8-bit roughly halves the estimate.
3. Raise the mode (Settings → Model loading guardrails), or click "load anyway". Only do this if you know nothing else
   big is running. The guardrail ignores other apps, so it won't protect you from swapping.

## Status

| Area | Status |
|---|---|
| Budget, Balanced, 32 GB Mac | ✅ measured: boundary at 25.600 GiB (`will-it-load probe`) |
| Budget, other modes / RAM sizes | 🟡 modelled, **run `will-it-load probe` and post the result** |
| Other apps' memory is ignored | ✅ measured (9 GiB held elsewhere didn't change the verdict) |
| MLX / safetensors estimate (× 1.4, context-independent) | ✅ measured: exact match to 0.01 GiB |
| Embedding models (× 1.4) | ✅ measured |
| Manually loaded models block JIT loads | ✅ measured |
| Windows / Linux (RAM + VRAM) | 🟡 modelled, **needs measurements**: [help wanted](CONTRIBUTING.md) |
| GGUF LLM estimate (context, KV cache, offload) | 🔴 not modelled yet: `verify` falls back to LM Studio's own estimate |

Verified on LM Studio **0.4.25** (macOS, Apple M1 Max, 32 GB). LM Studio updates can change any of this.
If something doesn't match, please [open a measurement report](../../issues/new?template=measurement.yml).

## Contributing

The most valuable contribution takes two minutes: run `will-it-load verify --json` (and, if you can,
`will-it-load probe --json`) and post the result. Especially useful
are Windows/Linux machines with a GPU, other RAM sizes and GGUF models. See [CONTRIBUTING.md](CONTRIBUTING.md),
including the rules on how we learn things about LM Studio: **black-box only, no decompiled code**.

## License

MIT © Nik Pottbecker. "LM Studio" is a trademark of its owner. It's used here only to say what this tool works with.
