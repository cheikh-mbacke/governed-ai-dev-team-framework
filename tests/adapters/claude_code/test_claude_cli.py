"""Real Claude Code CLI invocation — opt-in, mocked in this suite.

No test here ever spends real Claude usage: `invoke_claude_cli` is only
exercised with `subprocess.run` monkeypatched. The contract asserted below
(JSON envelope shape, --permission-mode bypassPermissions, opt-in env var)
was verified against two real, live, authenticated `claude -p` invocations
on 2026-09-15 (one hit --max-budget-usd, one completed) — see
adapters/claude_code/runtime/claude_cli.py's module docstring.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from adapters.claude_code.runtime import claude_cli
from adapters.claude_code.runtime.execute import execute_runtime

from governed_ai.adapters.common import agent_invocation
from governed_ai.adapters.spi import ExecutionRequest

BASE_SHA = "a" * 40


def _sample_request(execution_id: str = "EXE-CLAUDE-CLI-TEST") -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id=execution_id,
        correlation_id="COR-CLAUDE-CLI-TEST",
        adapter={"id": "claude-code", "version": "0.1.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": "control-plane",
            "role_revision": "1.0.0",
            "procedure_id": "orchestrator",
            "procedure_revision": "1.0.0",
        },
        project_id="claude-cli-test",
        work_unit_id="WU-CLAUDE-CLI-TEST",
        base_sha=BASE_SHA,
        requested_at="2026-09-15T18:00:00+00:00",
    )


def _write_work_unit(root: Path) -> None:
    (root / ".ai-team" / "work-units").mkdir(parents=True)
    wu = {
        "id": "WU-CLAUDE-CLI-TEST",
        "title": "Claude CLI test work unit",
        "objective": {"result": "prove the real invocation contract"},
        "scope": {"include": ["src/"], "exclude": ["docs/"]},
        "expected_behavior": "does the thing",
        "acceptance_criteria": ["it works"],
    }
    (root / ".ai-team" / "work-units" / "WU-CLAUDE-CLI-TEST.yaml").write_text(
        yaml.safe_dump(wu), encoding="utf-8"
    )


def test_invoke_claude_cli_returns_blocked_when_binary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: None)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request())
    assert outcome.status == "blocked"


def test_invoke_claude_cli_uses_print_and_bypass_permissions_no_trust_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code skips the workspace-trust dialog under -p (verified) — no
    --trust-equivalent flag exists or is needed, unlike Cursor's agent --trust."""
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: "claude")

    def _fake_run(command, **kwargs):
        assert "--print" in command
        assert "--permission-mode" in command
        assert "bypassPermissions" in command
        assert "--trust" not in command
        assert "--force" not in command
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 1671,
                    "result": json.dumps(
                        {
                            "summary": "OK",
                            "checks": [{"name": "tests", "status": "passed", "evidence_ref": "EV-1"}],
                            "artifacts": [],
                            "usage": {},
                        }
                    ),
                    "session_id": "bd969e00-54d1-4377-908b-590e84347728",
                    "uuid": "54ed2c1c-3d91-4bf8-8230-6c71df2c84d1",
                    "total_cost_usd": 0.0281,
                    "usage": {"input_tokens": 10, "output_tokens": 47},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request())
    assert outcome.status == "succeeded"
    assert outcome.summary == "OK"
    assert outcome.checks[0]["name"] == "tests"
    assert outcome.usage["input_tokens"] == 10
    assert outcome.usage["output_tokens"] == 47
    assert outcome.usage["total_tokens"] == 57
    assert outcome.usage["total_cost_usd"] == 0.0281
    assert outcome.duration_ms == 1671
    assert outcome.provider_session_id == "bd969e00-54d1-4377-908b-590e84347728"
    assert outcome.provider_request_id == "54ed2c1c-3d91-4bf8-8230-6c71df2c84d1"
    assert outcome.started_at
    assert outcome.finished_at


def test_invoke_claude_cli_parses_real_budget_exceeded_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verbatim shape captured from a real --max-budget-usd hit on 2026-09-15."""
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: "claude")

    def _fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=1,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "error_max_budget_usd",
                    "is_error": True,
                    "duration_ms": 4407,
                    "session_id": "f352394f-6aaf-40c6-95c5-22ad758809ca",
                    "total_cost_usd": 0.081,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                    "errors": ["Reached maximum budget ($0.05)"],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert any("maximum budget" in item for item in outcome.limitations)


def test_invoke_claude_cli_fails_when_handoff_missing_inside_success_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: "claude")

    def _fake_run(command, **kwargs):
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "I finished but forgot the JSON handoff.",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return subprocess.CompletedProcess(
            command, returncode=0, stdout=json.dumps(envelope), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert outcome.checks == []
    assert any("governed JSON handoff" in item for item in outcome.limitations)


def test_invoke_claude_cli_handles_non_json_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: "claude")

    def _fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, returncode=1, stdout="Unknown model: bogus.", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert "did not return the expected JSON envelope" in outcome.limitations[0]


def test_invoke_claude_cli_handles_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_cli, "resolve_claude_binary", lambda: "claude")

    def _fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = claude_cli.invoke_claude_cli(tmp_path, _sample_request(), timeout_seconds=1)
    assert outcome.status == "timed_out"


def test_running_claude_is_terminated_when_grant_is_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant_path = tmp_path / "grant.json"
    grant_path.write_text(
        '{"revoked_at":"2026-09-15T20:00:00+00:00","expires_at":"2099-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )

    class FakeProcess:
        returncode = 143
        pid = 5242

        def poll(self):
            return None

        def communicate(self, timeout=None):
            return "", ""

    process = FakeProcess()
    terminated: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        agent_invocation, "terminate_process_tree", lambda proc: terminated.append(proc)
    )
    completed, reason = claude_cli._run_claude_process(
        ["claude"],
        project_root=tmp_path,
        timeout_seconds=10,
        kill_switch_path=grant_path,
        allowed_shell_commands=["python -m pytest -q"],
        allowed_paths=["src/"],
    )
    assert completed is None
    assert reason == "authorization grant was revoked"
    assert terminated == [process]


def test_execute_runtime_defaults_to_stub_without_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing test suite (and any caller) must never pay for a real call by accident."""
    monkeypatch.delenv(agent_invocation.ENABLE_ENV_VAR, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("invoke_claude_cli must not be called without explicit opt-in")

    monkeypatch.setattr(
        "adapters.claude_code.runtime.execute.invoke_claude_cli", _fail_if_called
    )
    result = execute_runtime(tmp_path, _sample_request())
    assert result["status"] == "blocked"
    assert "not enabled" in result["limitations"][0]


def test_execute_runtime_uses_real_invocation_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(agent_invocation.ENABLE_ENV_VAR, "1")
    monkeypatch.setattr(
        "adapters.claude_code.runtime.execute.invoke_claude_cli",
        lambda project_root, request: agent_invocation.AgentInvocationOutcome(
            status="succeeded", summary="did the real thing", limitations=[]
        ),
    )
    result = execute_runtime(tmp_path, _sample_request())
    assert result["status"] == "succeeded"
    assert result["summary"] == "did the real thing"
