"""Focused tests for loop-engineering agent selection and fallback behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "_dev"
    / "loop-engineering"
    / "loop_engineering.py"
)
SPEC = importlib.util.spec_from_file_location("loop_engineering", MODULE_PATH)
assert SPEC and SPEC.loader
loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop
SPEC.loader.exec_module(loop)


def test_agy_command_is_noninteractive_and_accepts_edits():
    command = loop.agent_cmd("agy", 'implement "this"')

    assert command.startswith("agy --mode accept-edits")
    assert "--dangerously-skip-permissions" in command
    assert "--print-timeout 60m" in command


def test_grok_command_uses_installed_coding_model(monkeypatch):
    monkeypatch.setattr(loop, "agent_executable", lambda agent: r"C:\Tools\grok.exe")

    command = loop.agent_cmd("grok", "implement this")

    assert command.startswith(r'"C:\Tools\grok.exe" --model grok-4.5')
    assert "--permission-mode bypassPermissions" in command
    assert "--output-format plain -p" in command


def test_limit_blocked_coding_task_falls_back_to_agy(monkeypatch, tmp_path):
    calls = []
    fallback_state = {"active": False}
    results = iter(
        [
            loop.LoggedResult(1, 1, "You've hit your limit"),
            loop.LoggedResult(0, 10, ""),
            loop.LoggedResult(0, 10, ""),
        ]
    )

    def fake_run_logged(command, log_file):
        calls.append(command)
        return next(results)

    monkeypatch.setattr(loop, "run_logged", fake_run_logged)
    result = loop.run_agent(
        "claude", "make the change", tmp_path / "agent.log",
        fallback="agy", fallback_state=fallback_state,
    )

    assert result.returncode == 0
    assert fallback_state["active"] is True
    assert calls[0].startswith("claude -p")
    assert calls[1].startswith("agy --mode")

    loop.run_agent(
        "claude", "make another change", tmp_path / "agent.log",
        fallback="agy", fallback_state=fallback_state,
    )
    assert calls[2].startswith("agy --mode")


def test_non_limit_failure_does_not_fall_back(monkeypatch, tmp_path):
    calls = []

    def fake_run_logged(command, log_file):
        calls.append(command)
        return loop.LoggedResult(2, 3, "")

    monkeypatch.setattr(loop, "run_logged", fake_run_logged)
    result = loop.run_agent("claude", "make the change", tmp_path / "agent.log", fallback="agy")

    assert result.returncode == 2
    assert len(calls) == 1
