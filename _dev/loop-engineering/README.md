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

```bat
_dev\loop-engineering\run.bat --status            &:: where am I? what's next?
_dev\loop-engineering\run.bat --dry-run --phase 2 &:: what would run
_dev\loop-engineering\run.bat --phase 2           &:: finish phase 2
_dev\loop-engineering\run.bat --steps 1           &:: exactly one step
```

## How a step runs

1. **Guard** — dirty working tree is committed first, so every cycle starts clean.
2. **Execute** — `claude -p --permission-mode acceptEdits` gets the step's full
   description, its *Done when* criteria, and the working agreements.
3. **Validate** — the orchestrator itself runs `pytest`, `npm run test`, and
   `npm run build`. Agent claims are never trusted.
4. **Correct** — while red: a fixer prompt with the failure tail, up to
   `--max-fix-attempts` (default 3). Still red → **halt** with a log pointer.
5. **Review** — `codex exec` (or `--reviewer claude`) audits exactly that
   step's commit range, fixes what it finds; the board is re-validated.
6. **Done** — step recorded in `runtime/state.json`, pushed (unless `--no-push`).

## State

- Progress is auto-seeded from commit subjects matching `step N.N` /
  `steps N.N + N.N`; re-scan any time with `--sync-git`.
- Steps delivered outside that convention: `--mark-done-through 0.4`.
- The plan markdown is parsed live — editing the plan is enough; there is no
  second plan file to maintain.

## Cautions

- Don't run the loop while an interactive session edits the same repo —
  one writer at a time.
- Headless agents can't answer permission prompts: keep a project allowlist
  for git/npm/pytest in `.claude/settings.json`, or the run may stall.
- Watch the first live cycle end-to-end before leaving it unattended.
