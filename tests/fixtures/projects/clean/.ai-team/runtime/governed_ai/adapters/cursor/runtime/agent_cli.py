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
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime

DEFAULT_TIMEOUT_SECONDS = 600.0
ENABLE_ENV_VAR = "GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH"


def is_real_agent_launch_enabled() -> bool:
    return os.environ.get(ENABLE_ENV_VAR) == "1"


@dataclass(frozen=True, slots=True)
class AgentInvocationOutcome:
    status: str  # RuntimeStatus: succeeded | failed | blocked | timed_out
    summary: str
    limitations: list[str]
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    requested_commands: list[object] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    result_sha: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    provider_session_id: str | None = None
    provider_request_id: str | None = None


def resolve_agent_binary() -> str | None:
    return shutil.which("agent")


def build_prompt(project_root: Path, request: dict[str, Any]) -> str:
    """Best-effort prompt from the dispatched Work Unit and step.

    The prompt is assembled from authoritative Work Unit and contract data and
    requires a machine-verifiable handoff. Free-form success text is never
    enough to advance governed workflow state.
    """
    work_unit_id = request.get("work_unit_id", "")
    procedure_id = (request.get("contract") or {}).get("procedure_id", "")
    role_id = (request.get("contract") or {}).get("role_id", "")
    wu_path = project_root / ".ai-team" / "work-units" / f"{work_unit_id}.yaml"
    wu_summary = f"Work Unit id: {work_unit_id}\n"
    wu = dict(request.get("work_unit_snapshot") or {})
    if not wu and wu_path.is_file():
        wu = yaml.safe_load(wu_path.read_text(encoding="utf-8")) or {}
    if wu:
        wu_summary += (
            f"Title: {wu.get('title', '')}\n"
            f"Objective: {(wu.get('objective') or {}).get('result', '')}\n"
            f"Expected behavior: {wu.get('expected_behavior', '')}\n"
            f"Acceptance criteria: {wu.get('acceptance_criteria', [])}\n"
            f"Scope include: {(wu.get('scope') or {}).get('include', [])}\n"
            f"Scope exclude: {(wu.get('scope') or {}).get('exclude', [])}\n"
        )
    context = ""
    context_ref = request.get("context_package_ref")
    if context_ref:
        context_path = project_root / str(context_ref)
        if context_path.is_file():
            context = context_path.read_text(encoding="utf-8")[:20000]
    return (
        f"{wu_summary}\n"
        f"Role: {role_id}. Procedure: {procedure_id}.\n"
        f"Resolved scope: {request.get('resolved_scope', [])}.\n"
        f"Allowed shell commands: {request.get('allowed_shell_commands', [])}.\n"
        f"Allowed paths: {request.get('allowed_paths', [])}.\n"
        f"Context package:\n{context}\n"
        "Execute only this governed step. Stay strictly "
        "within the declared scope. Never modify constitution, governance, "
        "or .ai-team/schemas files. Do not target staging or production. "
        "For implementation, leave a coherent Git commit. Return ONLY a JSON object "
        "with keys summary, checks, artifacts, requested_commands and usage. "
        "Each successful check must contain name, status='passed', and evidence_ref. "
        "Each artifact must contain kind, path and sha256 prefixed by 'sha256:'. "
        "Do not claim success when required evidence is unavailable."
    )


def _parse_agent_stdout(stdout: str, stderr: str, returncode: int) -> AgentInvocationOutcome:
    text = stdout.strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        fallback = (text or stderr or "agent CLI produced no parseable output").strip()
        return AgentInvocationOutcome(
            status="failed",
            summary=fallback[:2000],
            limitations=["agent CLI did not return the expected JSON envelope"],
        )

    is_error = bool(payload.get("is_error"))
    result_text = str(payload.get("result") or "")
    status = "failed" if (is_error or returncode != 0) else "succeeded"
    structured: dict[str, Any] = {}
    if status == "succeeded":
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict):
                structured = parsed
        except json.JSONDecodeError:
            pass
    outer_usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    input_tokens = int(outer_usage.get("inputTokens", 0) or 0)
    output_tokens = int(outer_usage.get("outputTokens", 0) or 0)
    usage = dict(structured.get("usage") or {})
    usage.setdefault("input_tokens", input_tokens)
    usage.setdefault("output_tokens", output_tokens)
    usage.setdefault("total_tokens", input_tokens + output_tokens)
    limitations = []
    if status == "succeeded" and not structured:
        limitations.append("agent result was not the required governed JSON handoff")
    return AgentInvocationOutcome(
        status=status,
        summary=str(structured.get("summary") or result_text)[:4000],
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


def _git_head(project_root: Path) -> str | None:
    if not (project_root / ".git").exists():
        return None
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={project_root}", "rev-parse", "HEAD"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    value = completed.stdout.strip().lower()
    return value if completed.returncode == 0 and len(value) == 40 else None


def _kill_switch_reason(path: Path) -> str | None:
    """Return a fail-closed reason while a native agent is still running."""
    try:
        grant = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "authorization grant became unreadable"
    if grant.get("revoked_at"):
        return "authorization grant was revoked"
    expires_at = grant.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
        except ValueError:
            return "authorization grant expiry became invalid"
        if datetime.now(UTC) >= expiry:
            return "authorization grant expired"
    return None


def _sanitized_process_env(accessible_secrets: list[str]) -> dict[str, str]:
    """Expose only host essentials plus secret names explicitly approved by the grant."""
    essentials = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    approved = {str(name) for name in accessible_secrets}
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in essentials or key in approved
    }


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
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    """Run the CLI with a bounded watchdog that observes grant revocation."""
    process_env = _sanitized_process_env(accessible_secrets or [])
    process_env["GOVERNED_AI_UNATTENDED_RUN"] = "1"
    process_env["GOVERNED_AI_ALLOWED_SHELL_COMMANDS"] = json.dumps(allowed_shell_commands)
    process_env["GOVERNED_AI_ALLOWED_PATHS"] = json.dumps(allowed_paths)
    process_env["CURSOR_PROJECT_DIR"] = str(project_root.resolve())
    process_env.update(telemetry_context or {})
    process = subprocess.Popen(
        command,
        cwd=str(project_root),
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + timeout_seconds
    while True:
        reason = _kill_switch_reason(kill_switch_path)
        if reason is not None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            return None, reason
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            process.communicate()
            raise subprocess.TimeoutExpired(cmd=command, timeout=timeout_seconds)
        try:
            stdout, stderr = process.communicate(timeout=min(0.5, remaining))
        except subprocess.TimeoutExpired:
            continue
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr), None


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
            )
            if cancellation_reason is not None:
                return _with_timing(AgentInvocationOutcome(
                    status="cancelled",
                    summary=f"agent CLI stopped: {cancellation_reason}",
                    limitations=[],
                ))
            assert completed is not None
        else:
            process_env = _sanitized_process_env(
                [str(item) for item in request.get("accessible_secrets") or []]
            )
            process_env["CURSOR_PROJECT_DIR"] = str(project_root.resolve())
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
        object.__setattr__(outcome, "result_sha", _git_head(project_root))
    return _with_timing(outcome)
