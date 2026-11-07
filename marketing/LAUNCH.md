# Launch kit

Tone: helpful, factual, friendly towards LM Studio. We explain an opaque error and send people back into LM Studio
happier. Never "LM Studio is broken", never "we hacked/decompiled". Always: "measured", "verified against
`--estimate-only`", "unofficial".

Image for every post: `docs/assets/social-preview.png` (1280×640). Set it as the GitHub social preview too
(Settings → General → Social preview).

## Timing

| When | Where | Notes |
|---|---|---|
| Day 1, Tue–Thu 15:00–17:00 CET (US morning) | r/LocalLLaMA | Main audience. Post as a text post with the image, answer comments for 2 h. |
| Day 1, same time | r/LMStudio | Shorter version. |
| Day 2, 15:00 CET | Hacker News (Show HN) | Only if Reddit got traction. Link the repo, not the web page. |
| Day 2 | X / Bluesky / Mastodon thread | Tag nobody aggressively; @lmstudio may be mentioned once, politely. |
| Day 3 | LinkedIn (DE) | Personal story angle: "Fehlermeldung verstanden, Tool gebaut". |
| Later | LM Studio Discord, #community-projects or similar | Ask a moderator first whether self-promo is OK. |

Success signals to watch: measurement-report issues (that's the real goal), stars, Windows/Linux reports.

---

## r/LocalLLaMA

**Title:** I measured how LM Studio decides "insufficient system resources" and made a small calculator

**Body:**

> If you've hit *"Model loading was stopped due to insufficient system resources"* in LM Studio with plenty of free
> RAM, here's what's going on. I tested it against LM Studio's own `lms load --estimate-only` on 0.4.25:
>
> - **Your budget is smaller than your RAM.** Balanced = 75 % of the first 16 GiB + 85 % of the rest → 25.6 GiB on a
>   32 GB Mac (Strict 24.0, Relaxed 28.0).
> - **MLX models are estimated as file size × 1.4**, regardless of the context length you set. A 14 GB model counts
>   as about 20 GB.
> - **JIT loading only evicts other JIT models.** If you `lms load`-ed something, an API call for a different model can
>   fail even though that model alone fits. `lms unload --all` fixes it.
> - **Other apps' RAM isn't counted.** I held 9 GiB in another process and the verdict didn't change, so the guardrail
>   won't save you from swapping.
>
> I wrapped this into `will-it-load` (MIT, no dependencies, read-only):
> `uvx --from git+https://github.com/nikpottbecker/will-it-load will-it-load`
> There's also a browser version: https://nikpottbecker.github.io/will-it-load/
>
> It's unofficial and verified only on macOS so far. **If you're on Windows/Linux with a GPU, a
> `will-it-load verify --json` report would help a lot**: it only calls `--estimate-only`, nothing gets loaded.
> GGUF LLM estimates (context/KV-cache dependent) aren't modelled yet. PRs with measurements welcome.

## r/LMStudio (short)

> **Why "insufficient system resources"? Small calculator + findings (unofficial)**
> Balanced mode gives you 75 % of the first 16 GiB + 85 % above. MLX models count as file size × 1.4. JIT loads don't
> evict models you loaded manually. Details and a browser calculator:
> https://github.com/nikpottbecker/will-it-load. Measurement reports from other machines very welcome!

## Show HN

**Title:** Show HN: Will it load? – Predict LM Studio's model-loading guardrail

> LM Studio blocks model loads that it thinks would freeze your machine, but it doesn't say why. I measured the
> behaviour with its own dry-run command, wrote it down as a small model (budget per mode, a ×1.4 estimate for MLX
> models, JIT eviction rules) and built a CLI plus a static web calculator around it. CI replays every recorded
> measurement against both the Python and the JS implementation. It's unofficial and black-box only. Contributions
> are measurement reports from other hardware.

## X / Bluesky thread

1. LM Studio: "insufficient system resources". Me: 32 GB RAM, 12 GB model?? 🧵 I measured how the guardrail decides. 👇
2. Your budget isn't your RAM. Balanced = 75 % of the first 16 GiB + 85 % of the rest. 32 GB Mac → 25.6 GiB.
3. MLX models are estimated at file size × 1.4. Context length doesn't matter for the estimate.
4. The sneaky one: JIT loading only swaps out *JIT* models. `lms load` something manually and every API request for
   another model can fail. Fix: `lms unload --all`.
5. And: other apps' RAM isn't counted at all.
6. Calculator (browser, no install): https://nikpottbecker.github.io/will-it-load/ · CLI + findings:
   https://github.com/nikpottbecker/will-it-load (MIT, unofficial). Windows/Linux reports wanted! 🙏

## LinkedIn (Deutsch)

> Lokale KI auf dem Mac Studio: LM Studio meldete „insufficient system resources“, obwohl genug RAM frei war.
> Statt Einstellungen zu raten, habe ich das Verhalten systematisch mit LM Studios eigenem Probelauf vermessen:
>
> 🔹 Das Budget ist nicht der RAM: im Standardmodus 75 % der ersten 16 GiB + 85 % vom Rest
> 🔹 MLX-Modelle werden pauschal mit Dateigröße × 1,4 geschätzt
> 🔹 Manuell geladene Modelle blockieren Just-in-time-Loads über die API
>
> Daraus ist ein kleines Open-Source-Tool geworden, „will-it-load“, mit Web-Rechner, CLI und Tests gegen echte
> Messwerte. Wer LM Studio unter Windows oder Linux nutzt: Ein Messbericht hilft enorm.
> 👉 https://github.com/nikpottbecker/will-it-load
>
> #LocalLLM #AppleSilicon #OpenSource #KI

## Reply snippets

- *"Just turn guardrails off."* → You can, and for a single app on a dedicated machine that's fine. The tool helps
  when you want to keep the protection and understand it.
- *"Is this official?"* → No, it's community-made, and every number is checked against `lms load --estimate-only`.
  If LM Studio changes the behaviour, `verify` will show it.
- *"Where do the numbers come from / how do I know they're right?"* → Every claim is backed by measurements you can
  repeat: `--estimate-only` with different models, settings and loaded models, plus real load attempts. The data is in
  `data/measurements.json`, and `will-it-load verify` re-checks it on your machine.
