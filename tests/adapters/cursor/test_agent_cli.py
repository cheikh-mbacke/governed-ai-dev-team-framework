"""Real Cursor `agent` CLI invocation — opt-in, mocked in this suite (Document 6, orchestrator).

No test here ever spends real API credits: `invoke_agent_cli` is only
exercised with `subprocess.run` monkeypatched. The contract asserted below
(JSON envelope shape, --trust/--force flags, opt-in env var) was verified
against a real, live, authenticated invocation once, manually — see
docs/framework-design/requirements/mode-nuit-preuve-resilience-couverture.md for why
that kind of proof cannot live in the automated suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from adapters.cursor.runtime import agent_cli
from adapters.cursor.runtime.execute import execute_runtime

from governed_ai.adapters.spi import ExecutionRequest

BASE_SHA = "a" * 40


def _sample_request(execution_id: str = "EXE-AGENT-TEST") -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id=execution_id,
        correlation_id="COR-AGENT-TEST",
        adapter={"id": "cursor", "version": "1.0.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": "control-plane",
            "role_revision": "1.0.0",
            "procedure_id": "orchestrator",
            "procedure_revision": "1.0.0",
        },
        project_id="agent-cli-test",
        work_unit_id="WU-AGENT-TEST",
        base_sha=BASE_SHA,
        requested_at="2026-08-30T18:00:00+00:00",
    )


def _write_work_unit(root: Path) -> None:
    (root / ".ai-team" / "work-units").mkdir(parents=True)
    wu = {
        "id": "WU-AGENT-TEST",
        "title": "Agent CLI test work unit",
        "objective": {"result": "prove the real invocation contract"},
        "scope": {"include": ["src/"], "exclude": ["docs/"]},
        "expected_behavior": "does the thing",
        "acceptance_criteria": ["it works"],
    }
    (root / ".ai-team" / "work-units" / "WU-AGENT-TEST.yaml").write_text(
        yaml.safe_dump(wu), encoding="utf-8"
    )


def test_build_prompt_includes_work_unit_fields(tmp_path: Path) -> None:
    _write_work_unit(tmp_path)
    prompt = agent_cli.build_prompt(tmp_path, _sample_request())
    assert "Agent CLI test work unit" in prompt
    assert "prove the real invocation contract" in prompt
    assert "it works" in prompt
    assert "orchestrator" in prompt


def test_build_prompt_tolerates_missing_work_unit_file(tmp_path: Path) -> None:
    prompt = agent_cli.build_prompt(tmp_path, _sample_request())
    assert "WU-AGENT-TEST" in prompt


def test_build_prompt_loads_context_package_by_canonical_path(tmp_path: Path) -> None:
    packages = tmp_path / ".ai-team" / "context-packages"
    packages.mkdir(parents=True)
    (packages / "CTX-WU-AGENT-TEST.yaml").write_text(
        "id: CTX-WU-AGENT-TEST\nwork_unit: WU-AGENT-TEST\nrole: backend-developer\n"
        "items: []\n",
        encoding="utf-8",
    )
    request = _sample_request()
    request["context_package_ref"] = ".ai-team/context-packages/CTX-WU-AGENT-TEST.yaml"
    prompt = agent_cli.build_prompt(tmp_path, request)
    assert "CTX-WU-AGENT-TEST" in prompt


def test_build_prompt_resolves_bare_context_id(tmp_path: Path) -> None:
    packages = tmp_path / ".ai-team" / "context-packages"
    packages.mkdir(parents=True)
    (packages / "CTX-BARE.yaml").write_text(
        "id: CTX-BARE\nwork_unit: WU-AGENT-TEST\nrole: backend-developer\nitems: []\n",
        encoding="utf-8",
    )
    request = _sample_request()
    request["context_package_ref"] = "CTX-BARE"
    prompt = agent_cli.build_prompt(tmp_path, request)
    assert "CTX-BARE" in prompt


def test_build_prompt_ignores_context_path_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("id: LEAK\nsecret: yes\n", encoding="utf-8")
    request = _sample_request()
    request["context_package_ref"] = str(outside)
    prompt = agent_cli.build_prompt(tmp_path, request)
    assert "LEAK" not in prompt
    assert "secret" not in prompt


def test_invoke_agent_cli_returns_blocked_when_binary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: None)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "blocked"


def test_invoke_agent_cli_parses_successful_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")

    def _fake_run(command, **kwargs):
        assert "--trust" in command
        assert "--force" in command
        assert "--print" in command
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=(
                '{"type":"result","subtype":"success","is_error":false,'
                '"duration_ms":5203,"result":"{\\"summary\\":\\"OK\\",'
                '\\"checks\\":[{\\"name\\":\\"tests\\",\\"status\\":\\"passed\\",'
                '\\"evidence_ref\\":\\"EV-1\\"}],\\"artifacts\\":[],\\"usage\\":{}}",'
                '"session_id":"s1",'
                '"request_id":"r1","usage":{"inputTokens":1,"outputTokens":1}}'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "succeeded"
    assert outcome.summary == "OK"
    assert outcome.checks[0]["name"] == "tests"
    assert outcome.usage["input_tokens"] == 1
    assert outcome.usage["output_tokens"] == 1
    assert outcome.usage["total_tokens"] == 2
    assert outcome.duration_ms == 5203
    assert outcome.provider_session_id == "s1"
    assert outcome.provider_request_id == "r1"
    assert outcome.started_at
    assert outcome.finished_at


def test_invoke_agent_cli_parses_error_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")

    def _fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout='{"type":"result","subtype":"error","is_error":true,"result":"something broke"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert outcome.summary == "something broke"


def test_invoke_agent_cli_parses_prose_wrapped_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")
    inner = {
        "summary": "OK from prose wrap",
        "checks": [
            {"name": "AC-1", "status": "passed", "evidence_ref": "EV-1"},
        ],
        "artifacts": [],
        "usage": {},
    }
    result_text = "Working on it...\n" + json.dumps(inner)

    def _fake_run(command, **kwargs):
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 10,
            "result": result_text,
            "session_id": "s1",
            "request_id": "r1",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }
        return subprocess.CompletedProcess(
            command, returncode=0, stdout=json.dumps(envelope), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "succeeded"
    assert outcome.summary == "OK from prose wrap"
    assert outcome.checks[0]["name"] == "AC-1"


def test_invoke_agent_cli_fails_when_handoff_missing_inside_success_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")

    def _fake_run(command, **kwargs):
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "I finished but forgot the JSON handoff.",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }
        return subprocess.CompletedProcess(
            command, returncode=0, stdout=json.dumps(envelope), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert outcome.checks == []
    assert any("governed JSON handoff" in item for item in outcome.limitations)

    """Real behavior observed live: an invalid --model prints plain text and exits 1."""
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")

    def _fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, returncode=1, stdout="Cannot use this model: bogus.", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request())
    assert outcome.status == "failed"
    assert "did not return the expected JSON envelope" in outcome.limitations[0]


def test_invoke_agent_cli_handles_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_cli, "resolve_agent_binary", lambda: "agent")

    def _fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = agent_cli.invoke_agent_cli(tmp_path, _sample_request(), timeout_seconds=1)
    assert outcome.status == "timed_out"


def test_execute_runtime_defaults_to_stub_without_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing test suite (and any caller) must never pay for a real call by accident."""
    monkeypatch.delenv(agent_cli.ENABLE_ENV_VAR, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("invoke_agent_cli must not be called without explicit opt-in")

    monkeypatch.setattr(
        "adapters.cursor.runtime.execute.invoke_agent_cli", _fail_if_called
    )
    result = execute_runtime(tmp_path, _sample_request())
    assert result["status"] == "blocked"
    assert "not enabled" in result["limitations"][0]


def test_execute_runtime_uses_real_invocation_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(agent_cli.ENABLE_ENV_VAR, "1")
    monkeypatch.setattr(
        "adapters.cursor.runtime.execute.invoke_agent_cli",
        lambda project_root, request: agent_cli.AgentInvocationOutcome(
            status="succeeded", summary="did the real thing", limitations=[]
        ),
    )
    result = execute_runtime(tmp_path, _sample_request())
    assert result["status"] == "succeeded"
    assert result["summary"] == "did the real thing"


def test_running_agent_is_terminated_when_grant_is_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant_path = tmp_path / "grant.json"
    grant_path.write_text(
        '{"revoked_at":"2026-08-30T20:00:00+00:00","expires_at":"2099-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )

    class FakeProcess:
        returncode = 143
        pid = 4242

        def poll(self):
            return None

        def communicate(self, timeout=None):
            return "", ""

    process = FakeProcess()
    terminated: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        agent_cli, "_terminate_process_tree", lambda proc: terminated.append(proc)
    )
    completed, reason = agent_cli._run_agent_process(
        ["agent"],
        project_root=tmp_path,
        timeout_seconds=10,
        kill_switch_path=grant_path,
        allowed_shell_commands=["python -m pytest -q"],
        allowed_paths=["src/"],
    )
    assert completed is None
    assert reason == "authorization grant was revoked"
    assert terminated == [process]


def test_unattended_shell_hook_enforces_human_allowlist() -> None:
    hook = Path(__file__).resolve().parents[3] / ".cursor" / "hooks" / "guard_shell.py"
    environment = os.environ.copy()
    environment.update(
        {
            "GOVERNED_AI_UNATTENDED_RUN": "1",
            "GOVERNED_AI_ALLOWED_SHELL_COMMANDS": json.dumps(["python -m pytest -q"]),
            "GOVERNED_AI_ALLOWED_PATHS": json.dumps(["src/"]),
            "CURSOR_PROJECT_DIR": str(Path(__file__).resolve().parents[3]),
        }
    )
    allowed = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"command": "python -m pytest -q"}),
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=10,
    )
    denied = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"command": "whoami"}),
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=10,
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["permission"] == "allow"
    assert denied.returncode == 2
    assert json.loads(denied.stdout)["permission"] == "deny"

    malformed = subprocess.run(
        [sys.executable, str(hook)],
        input="{not-json",
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=10,
    )
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["permission"] == "deny"


def test_agent_watchdog_kills_a_real_timed_out_process(tmp_path: Path) -> None:
    grant_path = tmp_path / "grant.json"
    grant_path.write_text(
        '{"revoked_at":null,"expires_at":"2099-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    with pytest.raises(subprocess.TimeoutExpired):
        agent_cli._run_agent_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            project_root=tmp_path,
            timeout_seconds=0.1,
            kill_switch_path=grant_path,
            allowed_shell_commands=[],
            allowed_paths=["src/"],
        )
