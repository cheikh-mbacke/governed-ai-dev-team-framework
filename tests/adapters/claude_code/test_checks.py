"""adapters/claude_code/runtime/checks.py — preflight checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from adapters.claude_code.compiler.install_support import compile_claude_code_tree
from adapters.claude_code.runtime import checks

REPO_ROOT = Path(__file__).resolve().parents[3]


def _materialize_claude_dir(target: Path) -> None:
    compile_claude_code_tree(REPO_ROOT, target / ".claude")


def test_check_claude_binary_reports_pass_or_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)
    status, detail = checks.check_claude_binary()
    assert status == "pass"
    assert detail == "/usr/bin/claude"

    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    status, detail = checks.check_claude_binary()
    assert status == "fail"


def test_check_settings_config_missing(tmp_path: Path) -> None:
    status, detail = checks.check_settings_config(tmp_path)
    assert status == "fail"
    assert "missing" in detail


def test_check_settings_config_valid(tmp_path: Path) -> None:
    _materialize_claude_dir(tmp_path)
    status, _detail = checks.check_settings_config(tmp_path)
    assert status == "pass"


def test_probe_hook_missing_script_reports_false(tmp_path: Path) -> None:
    ok, detail = checks.probe_hook(tmp_path, "guard_shell.py", {})
    assert ok is False
    assert "missing" in detail


def test_probe_hook_guard_shell_allows_benign_command(tmp_path: Path) -> None:
    _materialize_claude_dir(tmp_path)
    ok, detail = checks.probe_hook(
        tmp_path, "guard_shell.py", {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    )
    assert ok is True
    assert "exit code 0" in detail


def test_probe_hook_guard_shell_blocks_dangerous_command(tmp_path: Path) -> None:
    _materialize_claude_dir(tmp_path)
    ok, detail = checks.probe_hook(
        tmp_path,
        "guard_shell.py",
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
    )
    assert ok is True  # exit code 2 is a recognized, expected outcome
    assert "exit code 2" in detail


def test_collect_preflight_report_has_expected_keys(tmp_path: Path) -> None:
    _materialize_claude_dir(tmp_path)
    report = checks.collect_preflight_report(tmp_path)
    assert "platform" in report
    assert "claude_binary" in report
    assert "settings_config" in report
    assert "guard_hook" in report
    assert "real_agent_launch" not in report

    unattended_report = checks.collect_preflight_report(tmp_path, unattended=True)
    assert "real_agent_launch" in unattended_report
