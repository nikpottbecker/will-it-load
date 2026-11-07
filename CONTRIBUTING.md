# Contributing

Thanks for helping! The project lives on measurements. The more machines and LM Studio versions we cover, the more
useful it gets.

## The ground rule: black-box only

We learn about LM Studio **only by observing how the installed program behaves**: running it, calling its public CLI
and API, feeding in different inputs and recording the outputs.

**Allowed**

- `lms load <model> --estimate-only`, `lms ls/ps --json`, the REST API, real load attempts, the app's UI, log files
  on your own machine, LM Studio's public docs and changelogs.
- Changing *your own* settings, for example to Custom mode, to run an experiment.

**Not allowed in this repository**

- Decompiling, deobfuscating, disassembling or unpacking LM Studio's application code, or describing findings that
  came from doing so.
- Copying any part of LM Studio's code, assets, strings or documentation into this repo.
- Bypassing licence checks or any other protection.

LM Studio's terms of use prohibit reverse engineering the software beyond what the law allows. Observing and testing
a program you're allowed to use is permitted in the EU (Art. 5(3) Directive 2009/24/EC, § 69d(3) German Copyright
Act), and it's all we need. PRs that don't follow this rule will be closed. See also [LEGAL.md](LEGAL.md).

## Two-minute contribution: a measurement report

```bash
uvx --from git+https://github.com/nikpottbecker/will-it-load will-it-load verify --json > report.json
```

Then open a [Measurement report](../../issues/new?template=measurement.yml) issue and paste the file. `verify` never
loads a model. It only calls `lms load --estimate-only`. The report contains your OS, CPU, RAM, guardrail mode and
model names, nothing else. Edit it if you like.

The most valuable reports right now:

- 🟢 Windows or Linux with an NVIDIA/AMD GPU (tests the RAM + VRAM rule)
- 🟢 Macs with 8, 16, 24, 48, 64, 96, 128 GB or more
- 🟢 GGUF LLMs at different context lengths
- 🟢 Any new LM Studio version

## Experiments we need

| ID | Question | How |
|---|---|---|
| **E1** | Are the percentages exact for every mode and RAM size? | `lms unload --all`, then `will-it-load probe --json` once per mode (switch the mode in LM Studio's settings between runs). It creates a placeholder model (sparse file, never loaded, deleted afterwards) and bisects the size where LM Studio's verdict flips. Measured so far: Balanced on 32 GB. |
| **E2** | Does Windows/Linux count RAM + VRAM? | `will-it-load verify --json --vram <your VRAM>` on a machine with a dedicated GPU, ideally with a model close to the predicted limit. |
| **E3** | How are GGUF LLM estimates calculated? | `lms load <gguf> --estimate-only -c <N>` for many N, `--gpu off/0.5/max`, `--parallel`. Fit a formula from model metadata (layers, heads, embedding size, quant). |
| **E4** | Did an update change anything? | Run `will-it-load verify` after every LM Studio update and post the report, even if everything matches. |

## Code contributions

```bash
git clone https://github.com/nikpottbecker/will-it-load && cd will-it-load
python -m pip install -e . pytest
python -m pytest            # Python model + replay of data/measurements.json
node docs/test-calculator.mjs  # web calculator, same data
python -m http.server -d docs  # preview the web calculator at http://localhost:8000
```

- The model lives in **two places** that must agree: `src/will_it_load/model.py` (CLI) and `docs/calculator.mjs`
  (web). CI checks both against `data/measurements.json`.
- When you change the model, add the measurements that justify it to `data/measurements.json` in the same PR, and
  update the evidence level in `docs/FINDINGS.md`.
- No runtime dependencies. Python 3.9+. Standard-library only.
- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Adding measurements to the dataset

Append the JSON from `verify --json` to `reports` in `data/measurements.json`, add `"scenario"` (what was loaded,
anything special) and `"lm_studio_version"`, and run the tests. If a test fails, that's a finding: open an issue or
adjust the model.
