"""Loop-engineering orchestrator for the workflow-builder upgrade.

Parses _dev/upgrade/implementation-plan.md into phases/steps (the markdown
stays the single source of truth), tracks progress in _dev/loop/state.json,
and drives an execute -> validate -> correct -> review -> commit cycle per
step until the requested phase (or step) is complete.

The orchestrator NEVER trusts an agent's claim of success: after every agent
invocation it runs pytest, vitest, and the production build itself, and only
a green board lets a step be marked done.

Usage (from the repo root):
    python _dev/loop_engineering.py --status            # plan + progress
    python _dev/loop_engineering.py --phase 2           # run until phase 2 done
    python _dev/loop_engineering.py --until 2.5         # run through step 2.5
    python _dev/loop_engineering.py --steps 1           # run exactly one step
    python _dev/loop_engineering.py --dry-run --phase 2 # show what would run
    python _dev/loop_engineering.py --mark-done-through 2.3
Options: --reviewer codex|claude|none  --no-push  --max-fix-attempts N
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "_dev" / "upgrade" / "implementation-plan.md"
LOOP_DIR = ROOT / "_dev" / "loop"
STATE_PATH = LOOP_DIR / "state.json"
LOG_DIR = LOOP_DIR / "logs"

PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
AGENT_TIMEOUT_S = 60 * 60          # one hour per agent invocation
VALIDATE_TIMEOUT_S = 15 * 60

STEP_RE = re.compile(r"^### (\d+\.\d+) (.+?)\s*$", re.M)
PHASE_RE = re.compile(r"^## Phase (\d+) — (.+?)\s*$", re.M)
DONE_WHEN_RE = re.compile(r"\*\*Done when:\*\*\s*(.+?)(?=\n\n|\n###|\n---|\n## |\Z)", re.S)
# Commits made so far use "step 2.3 - ..." and "steps 1.6 + 1.7 - ..."
COMMIT_STEP_RE = re.compile(r"steps? (\d+\.\d+)(?: \+ (\d+\.\d+))?")


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------

@dataclass
class Step:
    id: str
    title: str
    body: str
    done_when: str
    phase: int

    @property
    def sort_key(self):
        major, minor = self.id.split(".")
        return (int(major), int(minor))


@dataclass
class Plan:
    phases: dict[int, str] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def phase_steps(self, phase: int) -> list[Step]:
        return [s for s in self.steps if s.phase == phase]


def parse_plan(text: str) -> Plan:
    plan = Plan()
    for match in PHASE_RE.finditer(text):
        plan.phases[int(match.group(1))] = match.group(2)

    matches = list(STEP_RE.finditer(text))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        done = DONE_WHEN_RE.search(body)
        plan.steps.append(Step(
            id=match.group(1),
            title=match.group(2),
            body=body,
            done_when=done.group(1).strip() if done else "",
            phase=int(match.group(1).split(".")[0]),
        ))
    plan.steps.sort(key=lambda s: s.sort_key)
    return plan


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"done": [], "history": []}


def save_state(state: dict) -> None:
    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record(state: dict, step_id: str, event: str, detail: str = "") -> None:
    state["history"].append({
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "step": step_id,
        "event": event,
        "detail": detail[:400],
    })
    save_state(state)


def steps_done_in_git() -> set[str]:
    """Steps already delivered, inferred from commit subjects."""
    out = run_capture(["git", "log", "--oneline", "-200"], cwd=ROOT)
    done = set()
    for line in out.splitlines():
        for match in COMMIT_STEP_RE.finditer(line):
            done.add(match.group(1))
            if match.group(2):
                done.add(match.group(2))
    return done


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def run_capture(cmd, cwd=ROOT, timeout=120) -> str:
    result = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, shell=isinstance(cmd, str), encoding="utf-8", errors="replace",
    )
    return (result.stdout or "") + (result.stderr or "")


def run_logged(cmd, log_file: Path, cwd=ROOT, timeout=AGENT_TIMEOUT_S) -> int:
    """Run a command streaming combined output to console + log file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"\n===== {dt.datetime.now().isoformat()} :: {cmd}\n")
        log.flush()
        process = subprocess.Popen(
            cmd, cwd=str(cwd), shell=isinstance(cmd, str),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            log.write("\n!! TIMEOUT — process killed\n")
            return 124
        return process.returncode or 0


# ---------------------------------------------------------------------------
# Validation (never trust the agent)
# ---------------------------------------------------------------------------

def validate(log_file: Path) -> tuple[bool, str]:
    checks = [
        ("pytest", [str(PYTHON), "-m", "pytest", "tests/", "-q", "--tb=short"], ROOT),
        ("vitest", "npm run test", ROOT / "frontend"),
        ("build", "npm run build", ROOT / "frontend"),
    ]
    for name, cmd, cwd in checks:
        print(f"  [validate] {name} ...", flush=True)
        try:
            output = run_capture(cmd, cwd=cwd, timeout=VALIDATE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return False, f"{name} timed out"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as log:
            log.write(f"\n----- validate:{name}\n{output}\n")
        failed = (
            (name == "pytest" and (" failed" in output or "error" in output.lower().split("=")[-1]))
            or (name == "vitest" and " failed" in output)
            or (name == "build" and "✓ built" not in output and "built in" not in output)
        )
        if failed:
            tail = "\n".join(output.strip().splitlines()[-25:])
            return False, f"{name} FAILED:\n{tail}"
        print(f"  [validate] {name} OK")
    return True, "all green"


def working_tree_dirty() -> bool:
    return bool(run_capture(["git", "status", "--porcelain"]).strip())


def commit_all(message: str) -> None:
    run_capture(["git", "add", "-A"])
    run_capture(["git", "commit", "-m", message], timeout=300)


def head_commit() -> str:
    return run_capture(["git", "rev-parse", "--short", "HEAD"]).strip()


# ---------------------------------------------------------------------------
# Agent prompts
# ---------------------------------------------------------------------------

AGREEMENTS = (
    "Working agreements: implement ONLY this step (do not start other steps); "
    "follow existing conventions and _dev/upgrade/contracts.md; run pytest, "
    "'npm run test' and 'npm run build' (frontend/) and get them green BEFORE "
    "committing; finish with exactly one commit whose subject contains "
    "'step {step_id}'. Do not push."
)


def execute_prompt(step: Step) -> str:
    return (
        f"You are executing step {step.id} of the workflow-builder plan "
        f"(_dev/upgrade/implementation-plan.md). Step {step.id}: {step.title}.\n\n"
        f"Step description:\n{step.body}\n\n"
        f"Done when: {step.done_when}\n\n" + AGREEMENTS.format(step_id=step.id)
    )


def fix_prompt(step: Step, failure: str) -> str:
    return (
        f"The build/test board is RED after work on step {step.id} ({step.title}). "
        f"Diagnose and fix the failures below, re-run the suites until green, "
        f"then commit the fix with subject 'fix: step {step.id} validation'. "
        f"Do not start new features.\n\nFailure output:\n{failure}"
    )


def review_prompt(step: Step, before: str, after: str) -> str:
    return (
        f"Review the commits {before}..{after} implementing step {step.id} "
        f"({step.title}) of _dev/upgrade/implementation-plan.md. Hunt for real "
        f"bugs: correctness, contract violations vs _dev/upgrade/contracts.md, "
        f"security, edge cases. Fix what you find, run pytest and the frontend "
        f"suites until green, then commit fixes with subject "
        f"'fix(review): step {step.id}'. If nothing needs fixing, change nothing."
    )


def agent_cmd(agent: str, prompt: str) -> str:
    escaped = prompt.replace('"', "'")
    if agent == "codex":
        return f'codex exec "{escaped}"'
    return f'claude -p --permission-mode acceptEdits "{escaped}"'


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def run_step(step: Step, state: dict, args) -> bool:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{stamp}_step_{step.id.replace('.', '-')}.log"
    print(f"\n======== STEP {step.id} — {step.title} ========")
    record(state, step.id, "start")

    if working_tree_dirty():
        print("  [guard] working tree dirty — committing leftovers first")
        commit_all(f"chore(loop): absorb uncommitted changes before step {step.id}")

    baseline = head_commit()

    # 1) EXECUTE
    print("  [execute] launching builder agent")
    run_logged(agent_cmd("claude", execute_prompt(step)), log_file)
    if working_tree_dirty():
        commit_all(f"feat(workflow): step {step.id} - {step.title} (loop auto-commit)")

    # 2) VALIDATE + CORRECT loop
    for attempt in range(1, args.max_fix_attempts + 1):
        ok, detail = validate(log_file)
        if ok:
            break
        print(f"  [correct] validation red (attempt {attempt}): relaunching fixer")
        record(state, step.id, "validation_red", detail)
        run_logged(agent_cmd("claude", fix_prompt(step, detail)), log_file)
        if working_tree_dirty():
            commit_all(f"fix: step {step.id} validation (loop auto-commit)")
    else:
        record(state, step.id, "halt", "validation still red after max fix attempts")
        print(f"  [halt] step {step.id}: validation still red — human needed. Log: {log_file}")
        return False

    # 3) REVIEW (adversarial pass) + re-validate
    if args.reviewer != "none":
        print(f"  [review] launching {args.reviewer} reviewer")
        run_logged(agent_cmd(args.reviewer, review_prompt(step, baseline, head_commit())), log_file)
        if working_tree_dirty():
            commit_all(f"fix(review): step {step.id} (loop auto-commit)")
        ok, detail = validate(log_file)
        if not ok:
            print("  [correct] reviewer broke the board — one repair pass")
            record(state, step.id, "review_red", detail)
            run_logged(agent_cmd("claude", fix_prompt(step, detail)), log_file)
            if working_tree_dirty():
                commit_all(f"fix: step {step.id} post-review (loop auto-commit)")
            ok, detail = validate(log_file)
            if not ok:
                record(state, step.id, "halt", "red after review repair")
                print(f"  [halt] step {step.id} red after review repair. Log: {log_file}")
                return False

    # 4) DONE
    if step.id not in state["done"]:
        state["done"].append(step.id)
    record(state, step.id, "done", head_commit())
    if not args.no_push:
        print("  [push] pushing to origin")
        run_capture(["git", "push"], timeout=600)
    print(f"  [done] step {step.id} complete at {head_commit()}")
    return True


def pick_targets(plan: Plan, state: dict, args) -> list[Step]:
    done = set(state["done"])
    pending = [s for s in plan.steps if s.id not in done]
    if args.phase is not None:
        pending = [s for s in pending if s.phase == args.phase]
    if args.until:
        limit = plan.step(args.until)
        if not limit:
            sys.exit(f"Unknown step id: {args.until}")
        pending = [s for s in pending if s.sort_key <= limit.sort_key]
    if args.steps:
        pending = pending[: args.steps]
    return pending


def print_status(plan: Plan, state: dict) -> None:
    done = set(state["done"])
    print(f"Plan: {PLAN_PATH.name} — {len(plan.steps)} steps in {len(plan.phases)} phases\n")
    for phase, title in sorted(plan.phases.items()):
        steps = plan.phase_steps(phase)
        completed = sum(1 for s in steps if s.id in done)
        marker = "✔" if completed == len(steps) and steps else " "
        print(f" [{marker}] Phase {phase} — {title}  ({completed}/{len(steps)})")
        for step in steps:
            flag = "✔" if step.id in done else "·"
            print(f"      {flag} {step.id}  {step.title}")
    nxt = next((s for s in plan.steps if s.id not in done), None)
    print(f"\nNext step: {nxt.id} — {nxt.title}" if nxt else "\nAll steps complete.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="show plan progress and exit")
    ap.add_argument("--phase", type=int, help="run until this phase is complete")
    ap.add_argument("--until", help="run through this step id (e.g. 2.5)")
    ap.add_argument("--steps", type=int, help="run at most N steps")
    ap.add_argument("--dry-run", action="store_true", help="show what would run")
    ap.add_argument("--reviewer", choices=["codex", "claude", "none"], default="codex")
    ap.add_argument("--max-fix-attempts", type=int, default=3)
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--mark-done-through", metavar="STEP", help="mark all steps up to STEP as done")
    ap.add_argument("--sync-git", action="store_true", help="merge steps found in git log into done state")
    args = ap.parse_args()

    plan = parse_plan(PLAN_PATH.read_text(encoding="utf-8"))
    state = load_state()

    if args.sync_git or not state["done"]:
        found = steps_done_in_git() & {s.id for s in plan.steps}
        state["done"] = sorted(set(state["done"]) | found,
                               key=lambda i: (int(i.split(".")[0]), int(i.split(".")[1])))
        save_state(state)

    if args.mark_done_through:
        limit = plan.step(args.mark_done_through)
        if not limit:
            sys.exit(f"Unknown step id: {args.mark_done_through}")
        state["done"] = sorted(
            {s.id for s in plan.steps if s.sort_key <= limit.sort_key} | set(state["done"]),
            key=lambda i: (int(i.split(".")[0]), int(i.split(".")[1])))
        save_state(state)
        print(f"Marked done through {limit.id}.")

    if args.status or not (args.phase is not None or args.until or args.steps):
        print_status(plan, state)
        return

    targets = pick_targets(plan, state, args)
    if not targets:
        print("Nothing to do — selected scope is already complete.")
        return

    if args.dry_run:
        print("Would run, in order:")
        for step in targets:
            print(f"  {step.id}  {step.title}")
        return

    for step in targets:
        if not run_step(step, state, args):
            sys.exit(1)

    print("\nScope complete.")
    print(run_capture(["git", "log", "--oneline", "-8"]))


if __name__ == "__main__":
    main()
