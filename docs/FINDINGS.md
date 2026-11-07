# How LM Studio's model-loading guardrail behaves

Version observed: **LM Studio 0.4.25** (macOS 26, Apple M1 Max, 32 GB). Last checked: 2026-11-07.
This file describes **observable behaviour**: what LM Studio does with given inputs. It contains no LM Studio
source code. Every claim has an evidence level:

- ✅ **Measured**: reproduced with LM Studio's own `lms load --estimate-only` or real load attempts. The data is in
  [`data/measurements.json`](../data/measurements.json), and CI replays it.
- 🟡 **Modelled**: consistent with all measurements so far, but not yet pinned down by a dedicated experiment.
  [Help us measure it.](../CONTRIBUTING.md#experiments-we-need)
- 🔴 **Unknown**: not modelled.

## The decision

```
loads  ⇔  memory held by LM Studio's loaded models  +  estimate(new model)  ≤  budget(mode)
```

When the check fails, LM Studio aborts with *"Model loading was stopped due to insufficient system resources …"*.
For MLX models the message has no GB number, because LM Studio marks its MLX estimate as low-confidence.
`lms load --estimate-only` prints `Confidence: LOW` for these models.

## 1. Budget per mode

| Mode | First 16 GiB | Above 16 GiB | 16 GB machine | 32 GB | 64 GB | 128 GB |
|---|---|---|---|---|---|---|
| Strict | 65 % | 85 % | 10.4 GiB | 24.0 GiB | 51.2 GiB | 105.6 GiB |
| **Balanced** (default) | 75 % | 85 % | 12.0 GiB | 25.6 GiB | 52.8 GiB | 107.2 GiB |
| Relaxed | 85 % | 90 % | 13.6 GiB | 28.0 GiB | 56.8 GiB | 114.4 GiB |
| Custom | your fixed value | | | | | |
| Off | no limit | | | | | |

- ✅ **Balanced on a 32 GB Mac: measured at 25.600 GiB.** A placeholder model was bisected with `will-it-load probe`,
  and the verdict flips between estimates of 25.59999 and 25.60020 GiB with nothing loaded.
- 🟡 The other modes and RAM sizes follow the same layered rule in our model, but each one still needs a `probe` run
  (experiment E1).
- 🟡 **macOS counts RAM only.** Windows/Linux are modelled as **RAM + dedicated VRAM**. This needs measurements from
  Windows and Linux machines (experiment E2).
- ✅ Older `settings.json` files store the mode as `low` / `medium` / `high`. These behave like Strict / Balanced /
  Relaxed.

## 2. The estimate

- ✅ **MLX / safetensors models: file size × 1.4.** Exact to two decimals for 3 of 3 models.
  The file size is the model's `sizeBytes` from `lms ls --json`.
- ✅ **The context length doesn't change the MLX estimate.** `-c 2048`, `32768` and `131072` all gave 15.78 GiB for
  gpt-oss-20b.
- ✅ **Embedding models: file size × 1.4**, even when the file is a GGUF (nomic-embed-text-v1.5: 84 MB → 112.29 MiB).
- 🔴 **GGUF LLMs** get a detailed estimate that depends on context length, layer count, KV-cache quantisation, flash
  attention, batch sizes and GPU offload. That isn't modelled yet. `will-it-load verify` falls back to LM Studio's own
  number (experiment E3).

## 3. What counts as "already used"

- ✅ **Models loaded right now count.** With gpt-oss-20b (12.10 GB) loaded, Gemma (20.39 GiB estimate) and Devstral
  (19.74 GiB) flip from "may be loaded" to "will fail to load".
- ✅ **Memory used by other apps does *not* count.** While another process held 9.0 GiB of incompressible data,
  Gemma's verdict stayed "may be loaded", although 9.0 + 20.39 GiB > 25.6 GiB.
  Consequence: the guardrail won't protect you from swapping when ComfyUI, a game or a browser is using the RAM.
- ✅ **With no model loaded, nothing counts.** The boundary sits exactly at the budget.
- ✅ **A loaded model counts a bit more than its file size.** gpt-oss-20b (MLX, 11.27 GiB file, 32k context, idle)
  moved the boundary by 11.83 GiB. `will-it-load` uses file size + 0.58 GiB per loaded model.
  This is probably the model process's real memory use, so it will vary with model type, context and activity
  (🟡 for other models).

## 4. Just-in-time (JIT) loading

- ✅ With *"Unload previous JIT model on load"* enabled (default), a just-in-time load (an API request naming a model
  that isn't loaded) first unloads **other JIT-loaded models**, then runs the check.
- ✅ **Models loaded manually (`lms load`, the app's model picker) are never evicted** this way. They keep counting
  against the budget. Typical symptom: `lms load modelA`, then an API call for `modelB` fails with "insufficient
  system resources", although `modelB` alone fits.
- 🟡 `lms ps --json` shows `ttlMs: null` for manually loaded models. JIT loads normally carry the JIT TTL
  (default 3600 s). `will-it-load` uses this as a hint, but a manual `lms load --ttl …` looks the same.

## Experiments we need

See [CONTRIBUTING.md](../CONTRIBUTING.md#experiments-we-need): E1 (`will-it-load probe` on other machines and modes), E2 (Windows/Linux + VRAM),
E3 (GGUF LLM estimate), E4 (re-check after every LM Studio update).
