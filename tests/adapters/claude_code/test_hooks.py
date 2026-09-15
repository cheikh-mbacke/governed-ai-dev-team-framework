"""Claude Code hook scripts — functional tests against real subprocess invocation.

These exercise the hook scripts exactly as Claude Code would invoke them
(JSON on stdin, exit code as the decision channel) — not just that they
exist in the compiled manifest. The PreToolUse JSON payload shape
(tool_name/tool_input) is a best-effort mapping, not verified against a
real Claude Code session (see Document 3 §"Grain Claude Code résolu
partiellement"); these tests pin the behavior this repo relies on, so a
mismatch discovered later has one place to fix.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = (
    Path(__file__).resolve().parents[3] / "adapters" / "claude_code" / "templates" / ".claude" / "hooks"
)


def _run(script: str, payload: dict, *, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=10,
    )


def test_guard_shell_allows_benign_command() -> None:
    result = _run("guard_shell.py", {"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert result.returncode == 0


def test_guard_shell_blocks_force_push() -> None:
    result = _run(
        "guard_shell.py",
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main --force"}},
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_guard_shell_blocks_rm_rf_root() -> None:
    result = _run("guard_shell.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert result.returncode == 2


def test_guard_shell_blocks_terraform_destroy() -> None:
    result = _run(
        "guard_shell.py", {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}}
    )
    assert result.returncode == 2


def test_guard_shell_ignores_non_bash_tools() -> None:
    result = _run("guard_shell.py", {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
    assert result.returncode == 0


def test_guard_shell_unattended_run_enforces_command_allowlist() -> None:
    result = _run(
        "guard_shell.py",
        {"tool_name": "Bash", "tool_input": {"command": "curl https://example.com"}},
        env_extra={
            "GOVERNED_AI_UNATTENDED_RUN": "1",
            "GOVERNED_AI_ALLOWED_SHELL_COMMANDS": json.dumps(["git status"]),
            "GOVERNED_AI_ALLOWED_PATHS": json.dumps(["src/"]),
        },
    )
    assert result.returncode == 2


def test_guard_shell_unattended_run_allows_listed_command() -> None:
    result = _run(
        "guard_shell.py",
        {"tool_name": "Bash", "tool_input": {"command": "git status"}},
        env_extra={
            "GOVERNED_AI_UNATTENDED_RUN": "1",
            "GOVERNED_AI_ALLOWED_SHELL_COMMANDS": json.dumps(["git status"]),
            "GOVERNED_AI_ALLOWED_PATHS": json.dumps(["src/"]),
        },
    )
    assert result.returncode == 0


def test_session_init_flags_framework_source_workspace(tmp_path: Path) -> None:
    ai_team = tmp_path / ".ai-team"
    ai_team.mkdir()
    (ai_team / "project-profile.yaml").write_text(
        "repository_kind: framework_source\n", encoding="utf-8"
    )
    result = _run("session_init.py", {}, env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "framework_source (fabrication)" in context


def test_session_init_default_message_for_installed_project(tmp_path: Path) -> None:
    result = _run("session_init.py", {}, env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "compile-project" in context


def test_audit_event_writes_minimized_log_entry(tmp_path: Path) -> None:
    (tmp_path / ".ai-team").mkdir()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git status --porcelain"},
        "cwd": str(tmp_path),
    }
    result = _run("audit_event.py", payload, env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0
    log_path = tmp_path / ".ai-team" / "logs" / "claude-code-events.jsonl"
    assert log_path.is_file()
    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["adapter"]["id"] == "claude-code"
    assert record["event"]["command"]["executable"] == "git"
    # Raw command text must never be logged verbatim, only its hash/length.
    assert "porcelain" not in json.dumps(record)


def test_audit_event_respects_telemetry_disabled(tmp_path: Path) -> None:
    ai_team = tmp_path / ".ai-team"
    ai_team.mkdir()
    (ai_team / "project-profile.yaml").write_text(
        "telemetry:\n  collection: disabled\n", encoding="utf-8"
    )
    result = _run(
        "audit_event.py",
        {"hook_event_name": "Stop", "cwd": str(tmp_path)},
        env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert result.returncode == 0
    assert not (ai_team / "logs" / "claude-code-events.jsonl").exists()


def test_backup_push_is_noop_without_project_profile(tmp_path: Path) -> None:
    result = _run("backup_push.py", {}, env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0


def test_backup_push_is_noop_when_auto_push_disabled(tmp_path: Path) -> None:
    ai_team = tmp_path / ".ai-team"
    ai_team.mkdir()
    (ai_team / "project-profile.yaml").write_text("release:\n  auto_push_working_branches: false\n", encoding="utf-8")
    result = _run("backup_push.py", {}, env_extra={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0
