# Loop Engineering

Plan-aware orchestrator that executes the workflow-builder upgrade
([phases-plans/implementation-plan.md](phases-plans/implementation-plan.md))
step by step: **execute → validate → correct → review → commit**, until the
selected phase or step range is complete.

## Layout

| Path | What |
|---|---|
| `loop_engineering.py` | The orchestrator (single file, stdlib only) |
| `run.bat` | Launcher — forwards all arguments from anywhere |
| `runtime/state.json` | Progress + event history (gitignored) |
| `runtime/logs/` | Full agent/validation output per step (gitignored) |

## Quick start

Double-click `run.bat`, choose an agent profile, and run all remaining work
phase by phase. Four profiles are available: all Codex, all Claude, Codex build
with Claude fix/review, or Claude build with Codex fix/review. The window prints
the selected roles, current phase, step, and stage, and stays open with the final
exit code. Agent output and idle-process heartbeats appear in the main window.

```bat
_dev\loop-engineering\run.bat --status            &:: where am I? what's next?
_dev\loop-engineering\run.bat --dry-run --phase 2 &:: what would run
_dev\loop-engineering\run.bat --phase 2           &:: finish phase 2
_dev\loop-engineering\run.bat --steps 1           &:: exactly one step
_dev\loop-engineering\run.bat --all               &:: everything, step-level cycles
_dev\loop-engineering\run.bat --by-phase          &:: everything, PHASE-level cycles
```

`--by-phase` is the "one shot" mode: Codex builds every step of a phase
(each still validated individually so failures can't compound), then the
reviewer audits + smoke-tests the **whole phase's commits** in one pass and
fixes what it finds — only then does the loop advance to the next phase.

## How a step runs

1. **Guard** — dirty working tree is committed first, so every cycle starts clean.
2. **Execute** — `codex exec` gets the step's full
   description, its *Done when* criteria, and the working agreements.
3. **Validate** — the orchestrator itself runs `pytest`, `npm run test`, and
   `npm run build`. Agent claims are never trusted.
4. **Correct** — while red: Codex receives a fixer prompt with the failure tail, up to
   `--max-fix-attempts` (default 3). Still red → **halt** with a log pointer.
5. **Review** — Codex audits exactly that
   step's commit range, fixes what it finds; the board is re-validated.
6. **Done** — step recorded in `runtime/state.json`, pushed (unless `--no-push`).

Agent quota/rate-limit messages, nonzero exits, timeouts, silent exits, and
builder/fixer runs that produce no changes are hard failures. The loop halts
without marking that work complete. An interrupted phase review is shown as
`REVIEW INCOMPLETE` and is resumed before later phases on the next phase-mode run.

## State

- Progress is auto-seeded from commit subjects matching `step N.N` /
  `steps N.N + N.N`; re-scan any time with `--sync-git`.
- Steps delivered outside that convention: `--mark-done-through 0.4`.
- The plan markdown is parsed live — editing the plan is enough; there is no
  second plan file to maintain.

## Cautions

- Don't run the loop while an interactive session edits the same repo —
  one writer at a time.
- Headless agents cannot answer interactive permission prompts; keep Codex's
  non-interactive execution permissions configured for this trusted workspace.
- Watch the first live cycle end-to-end before leaving it unattended.
