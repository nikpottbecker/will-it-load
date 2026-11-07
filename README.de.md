# Will it load? 🧮 (Deutsch)

**Warum sagt LM Studio „insufficient system resources“, und lädt mein nächstes Modell?**

> Inoffizielles Community-Projekt, nicht mit LM Studio / Element Labs verbunden. Siehe [LEGAL.md](LEGAL.md).

LM Studio hat eine Schutzfunktion, die **Model Loading Guardrails**. Sie verhindert, dass ein Modell den Rechner
einfrieren lässt. Wenn sie blockiert, sagt sie aber nicht, warum. `will-it-load` zeigt die Zahlen dahinter:
**Budget**, **Schätzung** und **bereits belegter Speicher**. Jede Vorhersage wird mit LM Studios eigenem Probelauf
(`lms load --estimate-only`) abgeglichen.

## Die drei Fakten hinter den meisten Fehlern

1. **Das Budget ist kleiner als dein RAM.** Balanced = 75 % der ersten 16 GiB + 85 % vom Rest. Auf einem 32-GB-Mac
   sind das **25,6 GiB** (Strict 24,0, Relaxed 28,0).
2. **MLX-Modelle werden mit Dateigröße × 1,4 geschätzt**, egal welche Kontextlänge du einstellst.
3. **Just-in-time-Loading verdrängt nur andere JIT-Modelle.** Ein per `lms load` oder in der App geladenes Modell bleibt
   geladen und blockiert die nächste API-Anfrage für ein anderes Modell.

Außerdem: **Speicher anderer Apps (ComfyUI, Browser, Spiele) zählt nicht mit.** Die Guardrail schützt also nicht vor
Swapping.

## Ausprobieren

- Im Browser: <https://nikpottbecker.github.io/will-it-load/>
- Im Terminal: `uvx --from git+https://github.com/nikpottbecker/will-it-load will-it-load`

Befehle, Status und Details stehen im [englischen README](README.md) und in [docs/FINDINGS.md](docs/FINDINGS.md).
Mitmachen: [CONTRIBUTING.md](CONTRIBUTING.md). Am meisten hilft ein Messbericht (`will-it-load verify --json`).
