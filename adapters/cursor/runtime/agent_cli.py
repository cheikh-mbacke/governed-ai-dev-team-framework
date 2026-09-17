"""Real invocation of the Cursor `agent` CLI.

The contract below was discovered by probing `agent --help` and a live,
authenticated invocation directly (2026-08-30) — it is not documented
anywhere upstream, and `adapters/cursor/runtime/checks.py` previously only
ever checked for the binary's presence on PATH (`shutil.which("agent")`),
never invoked it.

Observed contract:
  agent --print --output-format json --workspace <dir> --trust --force
        [--model <model>] "<prompt>"

- `--print` switches to non-interactive/scriptable mode. Without `--trust`
  it still blocks on an interactive workspace-trust prompt even under
  `--print` — exactly the invisible-blocking risk Document 6 §9.6 describes.
  `--force` (a.k.a. `--yolo`) is required for it to run shell/write tool
  calls without prompting; passing it here is not a new escalation, since
  the caller (`run_scheduling_tick`) only reaches this point after the
  Work Unit's `execution_ceiling` already authorized this exact capability.
- On success it prints one JSON object to stdout:
    {"type":"result","subtype":"success","is_error":false,
     "duration_ms":...,"result":"<text>","session_id":"...",
     "request_id":"...","usage":{...}}
- Some pre-flight validation errors (e.g. an unknown --model) print plain
  text instead of JSON and exit non-zero — treated as a hard failure here,
  not parsed as a result.

Real invocation costs real API credits and can execute arbitrary shell
commands / file writes on the target workspace. It is opt-in only — see
`is_real_agent_launch_enabled()` — so the existing test suite (and any
caller that does not explicitly opt in) keeps getting the pre-existing
stub behavior in `execute.py`, unchanged and free.

Prompt assembly, the kill-switch/Run-state watchdog, sanitized subprocess
environment and process-tree teardown live in
``governed_ai.adapters.common.agent_invocation`` — none of that was
Cursor-specific; only the binary name, its flags, and its JSON envelope
shape are.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from governed_ai.adapters.common.agent_invocation import (
    DEFAULT_TIMEOUT_SECONDS,
    ENABLE_ENV_VAR,  # noqa: F401 — re-exported, imported by name in checks.py/tests
    AgentInvocationOutcome,
    build_prompt,
    git_head,
    is_real_agent_launch_enabled,  # noqa: F401 — re-exported, imported by checks.py
    sanitized_process_env,
)
from governed_ai.adapters.common.agent_invocation import (
    run_agent_process as _shared_run_agent_process,
)
from governed_ai.compat.datetime import UTC, datetime

from .results import HANDOFF_DIAGNOSTIC_MAX, HANDOFF_SUMMARY_MAX, extract_governed_handoff

CURSOR_PROJECT_DIR_ENV_VAR = "CURSOR_PROJECT_DIR"


def resolve_agent_binary() -> str | None:
    return shutil.which("agent")


def _parse_agent_stdout(stdout: str, stderr: str, returncode: int) -> AgentInvocationOutcome:
    text = stdout.strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        fallback = (text or stderr or "agent CLI produced no parseable output").strip()
        return AgentInvocationOutcome(
            status="failed",
            summary=fallback[:HANDOFF_DIAGNOSTIC_MAX],
            limitations=["agent CLI did not return the expected JSON envelope"],
        )

    is_error = bool(payload.get("is_error"))
    result_text = str(payload.get("result") or "")
    status = "failed" if (is_error or returncode != 0) else "succeeded"
    structured: dict[str, Any] = {}
    limitations: list[str] = []
    if status == "succeeded":
        structured_handoff, extract_error = extract_governed_handoff(result_text)
        if structured_handoff is not None:
            structured = structured_handoff
        else:
            status = "failed"
            limitations.append(
                extract_error or "agent result was not the required governed JSON handoff"
            )
    outer_usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    input_tokens = int(outer_usage.get("inputTokens", 0) or 0)
    output_tokens = int(outer_usage.get("outputTokens", 0) or 0)
    usage = dict(structured.get("usage") or {})
    usage.setdefault("input_tokens", input_tokens)
    usage.setdefault("output_tokens", output_tokens)
    usage.setdefault("total_tokens", input_tokens + output_tokens)
    if structured:
        summary = str(structured.get("summary") or "")[:HANDOFF_SUMMARY_MAX]
    else:
        summary = (result_text or stderr or text)[:HANDOFF_DIAGNOSTIC_MAX]
    return AgentInvocationOutcome(
        status=status,
        summary=summary,
        limitations=limitations,
        checks=list(structured.get("checks") or []),
        artifacts=list(structured.get("artifacts") or []),
        requested_commands=list(structured.get("requested_commands") or []),
        usage=usage,
        duration_ms=(
            int(payload["duration_ms"])
            if isinstance(payload.get("duration_ms"), (int, float))
            else None
        ),
        provider_session_id=(str(payload["session_id"]) if payload.get("session_id") else None),
        provider_request_id=(str(payload["request_id"]) if payload.get("request_id") else None),
    )


def _run_agent_process(
    command: list[str],
    *,
    project_root: Path,
    timeout_seconds: float,
    kill_switch_path: Path,
    allowed_shell_commands: list[str],
    allowed_paths: list[str],
    accessible_secrets: list[str] | None = None,
    telemetry_context: dict[str, str] | None = None,
    run_state_path: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    return _shared_run_agent_process(
        command,
        project_root=project_root,
        timeout_seconds=timeout_seconds,
        kill_switch_path=kill_switch_path,
        allowed_shell_commands=allowed_shell_commands,
        allowed_paths=allowed_paths,
        project_dir_env_var=CURSOR_PROJECT_DIR_ENV_VAR,
        accessible_secrets=accessible_secrets,
        telemetry_context=telemetry_context,
        run_state_path=run_state_path,
    )


def invoke_agent_cli(
    project_root: Path,
    request: dict[str, Any],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> AgentInvocationOutcome:
    started_at = datetime.now(UTC)

    def _with_timing(outcome: AgentInvocationOutcome) -> AgentInvocationOutcome:
        finished_at = datetime.now(UTC)
        object.__setattr__(outcome, "started_at", started_at.isoformat())
        object.__setattr__(outcome, "finished_at", finished_at.isoformat())
        if outcome.duration_ms is None:
            object.__setattr__(
                outcome,
                "duration_ms",
                max(0, int((finished_at - started_at).total_seconds() * 1000)),
            )
        return outcome

    binary = resolve_agent_binary()
    if binary is None:
        return _with_timing(AgentInvocationOutcome(
            status="blocked",
            summary="Cursor `agent` CLI not found on PATH.",
            limitations=["agent binary unavailable"],
        ))

    command = [
        binary,
        "--print",
        "--output-format",
        "json",
        "--workspace",
        str(project_root),
        "--trust",
        "--force",
    ]
    model = request.get("model")
    if model:
        command.extend(["--model", str(model)])
    command.append(build_prompt(project_root, request))

    telemetry_context = {
        "GOVERNED_AI_EXECUTION_ID": str(request.get("execution_id") or ""),
        "GOVERNED_AI_RUN_ID": str(request.get("correlation_id") or ""),
        "GOVERNED_AI_WORK_UNIT_ID": str(request.get("work_unit_id") or ""),
        "GOVERNED_AI_ROLE_ID": str((request.get("contract") or {}).get("role_id") or ""),
    }

    kill_switch = request.get("kill_switch_path")
    try:
        if kill_switch:
            completed, cancellation_reason = _run_agent_process(
                command,
                project_root=project_root,
                timeout_seconds=timeout_seconds,
                kill_switch_path=Path(str(kill_switch)),
                allowed_shell_commands=[
                    str(item) for item in request.get("allowed_shell_commands") or []
                ],
                allowed_paths=[str(item) for item in request.get("allowed_paths") or []],
                accessible_secrets=[
                    str(item) for item in request.get("accessible_secrets") or []
                ],
                telemetry_context=telemetry_context,
                run_state_path=(
                    Path(str(request["run_state_path"]))
                    if request.get("run_state_path")
                    else None
                ),
            )
            if cancellation_reason is not None:
                return _with_timing(AgentInvocationOutcome(
                    status="cancelled",
                    summary=f"agent CLI stopped: {cancellation_reason}",
                    limitations=[],
                ))
            assert completed is not None
        else:
            process_env = sanitized_process_env(
                [str(item) for item in request.get("accessible_secrets") or []]
            )
            process_env[CURSOR_PROJECT_DIR_ENV_VAR] = str(project_root.resolve())
            process_env.update(telemetry_context)
            completed = subprocess.run(
                command,
                cwd=str(project_root),
                env=process_env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return _with_timing(AgentInvocationOutcome(
            status="timed_out",
            summary=f"agent CLI exceeded {timeout_seconds}s timeout",
            limitations=[],
        ))

    outcome = _parse_agent_stdout(completed.stdout, completed.stderr, completed.returncode)
    if outcome.status == "succeeded":
        object.__setattr__(outcome, "result_sha", git_head(project_root))
    return _with_timing(outcome)
