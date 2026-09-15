"""Real invocation of the Claude Code CLI.

Contract verified by hand against a live, authenticated invocation
(2026-09-15) — `claude --help` and two real `claude -p` calls (one hitting
`--max-budget-usd`, one completing) — not by reading upstream docs. Unlike
the hooks (Document 3 §"Grain Claude Code résolu partiellement"), this
contract IS first-hand verified, the same way Cursor's `agent --help`
contract was probed before `agent_cli.py` was written.

Observed contract:
  claude -p --output-format json [--model <model>]
        --permission-mode bypassPermissions --no-session-persistence "<prompt>"

- `-p`/`--print` switches to non-interactive mode. Per `claude --help`, the
  workspace-trust dialog is *already* skipped in this mode — no `--trust`-
  equivalent flag is needed, unlike Cursor's `agent --trust`.
- `--permission-mode bypassPermissions` is the equivalent of Cursor's
  `--force`: without it, a permission decision that would otherwise prompt
  a human has no TTY to prompt in non-interactive mode, and the actual
  fail-open/fail-closed behavior of an unanswered prompt under `-p` was not
  probed here. Passing it here is not a new escalation for the same reason
  `--force` isn't for Cursor: the caller only reaches this point after the
  Work Unit's `execution_ceiling` already authorized this exact capability,
  and `.claude/settings.json`'s `permissions.deny` plus `guard_shell.py`
  (PreToolUse exit 2) remain the actual enforcement layer — matching
  Document 3 §4.7 ("ne pas dépendre d'un hook/mode comme unique barrière").
- On success it prints one JSON object to stdout. Verified fields:
    {"type":"result","subtype":"success","is_error":false,
     "duration_ms":...,"result":"<text>","session_id":"...","uuid":"...",
     "total_cost_usd":...,"usage":{"input_tokens":...,"output_tokens":...,
     "cache_creation_input_tokens":...,"cache_read_input_tokens":...},
     "modelUsage":{...},"stop_reason":"end_turn","num_turns":1,
     "terminal_reason":"completed"}
  Note the *inner* `usage.input_tokens`/`usage.output_tokens` are already
  snake_case here — unlike Cursor's `usage.inputTokens`/`outputTokens` — so
  this adapter's stdout parser is not reusable for Cursor's envelope or
  vice versa. There is no `request_id` field; `uuid` is the closest
  equivalent and is used as `provider_request_id` below.
- A budget/error outcome instead carries `"is_error":true`, an `"errors"`
  list, and omits `"result"`/`"terminal_reason"`/`"api_error_status"` —
  verified via `--max-budget-usd` during probing.

Real invocation costs real Claude usage (subscription allowance or API
tokens, whichever the local `claude` CLI is authenticated with) and can
execute arbitrary shell/file-write tool calls in the target workspace. It
is opt-in only — see `is_real_agent_launch_enabled()`, shared with Cursor's
adapter — so the existing test suite keeps getting the pre-existing stub
behavior in `execute.py`, unchanged and free.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from governed_ai.adapters.common.agent_invocation import (
    DEFAULT_TIMEOUT_SECONDS,
    ENABLE_ENV_VAR,  # noqa: F401 — re-exported for parity with agent_cli.py
    AgentInvocationOutcome,
    build_prompt,
    git_head,
    is_real_agent_launch_enabled,  # noqa: F401 — re-exported, imported by execute.py
    sanitized_process_env,
)
from governed_ai.adapters.common.agent_invocation import (
    run_agent_process as _shared_run_agent_process,
)
from governed_ai.compat.datetime import UTC, datetime

from .results import HANDOFF_DIAGNOSTIC_MAX, HANDOFF_SUMMARY_MAX, extract_governed_handoff

CLAUDE_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"


def resolve_claude_binary() -> str | None:
    return shutil.which("claude")


def _parse_claude_stdout(stdout: str, stderr: str, returncode: int) -> AgentInvocationOutcome:
    text = stdout.strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        fallback = (text or stderr or "claude CLI produced no parseable output").strip()
        return AgentInvocationOutcome(
            status="failed",
            summary=fallback[:HANDOFF_DIAGNOSTIC_MAX],
            limitations=["claude CLI did not return the expected JSON envelope"],
        )

    is_error = bool(payload.get("is_error"))
    result_text = str(payload.get("result") or "")
    status = "failed" if (is_error or returncode != 0) else "succeeded"
    structured: dict[str, Any] = {}
    limitations: list[str] = []
    if is_error:
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            limitations.append("; ".join(str(item) for item in errors))
    if status == "succeeded":
        structured_handoff, extract_error = extract_governed_handoff(result_text)
        if structured_handoff is not None:
            structured = structured_handoff
        else:
            status = "failed"
            limitations.append(
                extract_error or "claude result was not the required governed JSON handoff"
            )
    outer_usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    input_tokens = int(outer_usage.get("input_tokens", 0) or 0)
    output_tokens = int(outer_usage.get("output_tokens", 0) or 0)
    usage = dict(structured.get("usage") or {})
    usage.setdefault("input_tokens", input_tokens)
    usage.setdefault("output_tokens", output_tokens)
    usage.setdefault("total_tokens", input_tokens + output_tokens)
    total_cost_usd = payload.get("total_cost_usd")
    if isinstance(total_cost_usd, (int, float)):
        usage.setdefault("total_cost_usd", total_cost_usd)
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
        provider_request_id=(str(payload["uuid"]) if payload.get("uuid") else None),
    )


def _run_claude_process(
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
        project_dir_env_var=CLAUDE_PROJECT_DIR_ENV_VAR,
        accessible_secrets=accessible_secrets,
        telemetry_context=telemetry_context,
        run_state_path=run_state_path,
    )


def invoke_claude_cli(
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

    binary = resolve_claude_binary()
    if binary is None:
        return _with_timing(AgentInvocationOutcome(
            status="blocked",
            summary="Claude Code `claude` CLI not found on PATH.",
            limitations=["claude binary unavailable"],
        ))

    command = [
        binary,
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
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
            completed, cancellation_reason = _run_claude_process(
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
                    summary=f"claude CLI stopped: {cancellation_reason}",
                    limitations=[],
                ))
            assert completed is not None
        else:
            process_env = sanitized_process_env(
                [str(item) for item in request.get("accessible_secrets") or []]
            )
            process_env[CLAUDE_PROJECT_DIR_ENV_VAR] = str(project_root.resolve())
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
            summary=f"claude CLI exceeded {timeout_seconds}s timeout",
            limitations=[],
        ))

    outcome = _parse_claude_stdout(completed.stdout, completed.stderr, completed.returncode)
    if outcome.status == "succeeded":
        object.__setattr__(outcome, "result_sha", git_head(project_root))
    return _with_timing(outcome)
