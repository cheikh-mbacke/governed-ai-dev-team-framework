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
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.domain.run.path_policy import sanitize_allowed_paths

from .results import HANDOFF_DIAGNOSTIC_MAX, HANDOFF_SUMMARY_MAX, extract_governed_handoff

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


def _unwrap_origin_bucket(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _format_design_context_section(
    context_package: dict[str, Any],
    *,
    visual_attachments: list[Any] | None = None,
) -> str:
    """Render the multimodal design slice carried on the execution request."""
    design = context_package.get("design")
    if not isinstance(design, dict) or not design:
        # Still allow a design-less package to advertise materialized attachments.
        if not visual_attachments:
            return ""
        design = {}
    contract = design.get("design_contract")
    if not isinstance(contract, dict):
        contract = {}

    routes = _unwrap_origin_bucket(contract.get("routes"))
    if routes is None:
        routes = design.get("routes")
    screens = design.get("screens")
    if screens is None:
        screens = _unwrap_origin_bucket(contract.get("screens"))
    states = design.get("states_to_implement")
    if states is None:
        states = _unwrap_origin_bucket(contract.get("states"))
    viewports = _unwrap_origin_bucket(contract.get("viewports"))
    if viewports is None:
        viewports = design.get("viewports")
    tolerances = _unwrap_origin_bucket(contract.get("tolerances"))
    if tolerances is None:
        tolerances = design.get("tolerances")
    free_zones = design.get("permitted_freedoms")
    if free_zones is None:
        free_zones = _unwrap_origin_bucket(contract.get("free_zones"))
    known_divergences = (
        design.get("known_divergences")
        or design.get("divergences")
        or contract.get("known_divergences")
        or []
    )

    lines = [
        "Design Context:",
        f"  design_mode: {design.get('design_mode') or ''}",
        f"  design_contract_id: {design.get('design_contract_id') or ''}",
        f"  design_contract_hash: {design.get('design_contract_hash') or ''}",
        f"  routes: {routes if routes is not None else []}",
        f"  screens: {screens if screens is not None else []}",
        f"  states: {states if states is not None else []}",
        f"  viewports: {viewports if viewports is not None else []}",
        f"  tolerances: {tolerances if tolerances is not None else {}}",
        f"  free_zones: {free_zones if free_zones is not None else []}",
        f"  known_divergences: {known_divergences}",
    ]
    if isinstance(visual_attachments, list) and visual_attachments:
        lines.append("  visual_attachments:")
        for item in visual_attachments:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            digest = str(item.get("content_hash") or "")
            artifact_id = str(item.get("design_artifact_id") or "")
            lines.append(
                f"    - path={path}"
                + (f" hash={digest}" if digest else "")
                + (f" artifact={artifact_id}" if artifact_id else "")
            )
    return "\n".join(lines) + "\n"


def _format_visual_attachments_section(request: dict[str, Any]) -> str:
    """List real attachment paths only — never claim an image without a path."""
    attachments = request.get("visual_attachments")
    if not isinstance(attachments, list):
        return ""
    lines: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        digest = str(item.get("content_hash") or "")
        artifact_id = str(item.get("design_artifact_id") or "")
        lines.append(
            f"ATTACHED DESIGN REFERENCE (read this file): {path}"
            + (f" (hash={digest})" if digest else "")
            + (f" [artifact={artifact_id}]" if artifact_id else "")
        )
    if not lines:
        return ""
    return "Visual attachments (workspace files):\n" + "\n".join(lines) + "\n"


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

    context_package = request.get("context_package")
    design_section = ""
    context = ""
    visual_attachments = request.get("visual_attachments")
    if isinstance(context_package, dict):
        # Prefer the in-request package over loading context_package_ref YAML.
        design_section = _format_design_context_section(
            context_package,
            visual_attachments=(
                visual_attachments if isinstance(visual_attachments, list) else None
            ),
        )
        try:
            context = yaml.safe_dump(context_package, sort_keys=False)[:20000]
        except (TypeError, ValueError, yaml.YAMLError):
            context = str(context_package)[:20000]
    else:
        context_ref = request.get("context_package_ref")
        if context_ref:
            packages_root = (project_root / ".ai-team" / "context-packages").resolve()
            ref_text = str(context_ref).strip().replace("\\", "/")
            candidates: list[Path] = []
            if ref_text and ".." not in Path(ref_text).parts and not (
                ref_text.startswith("/") or re.match(r"^[A-Za-z]:", ref_text)
            ):
                if ref_text.endswith(".yaml") and ref_text.startswith(
                    ".ai-team/context-packages/"
                ):
                    candidates.append((project_root / ref_text).resolve())
                elif "/" not in ref_text and not ref_text.startswith("."):
                    name = ref_text if ref_text.endswith(".yaml") else f"{ref_text}.yaml"
                    candidates.append((packages_root / name).resolve())
            for context_path in candidates:
                try:
                    context_path.relative_to(packages_root)
                except ValueError:
                    continue
                if context_path.is_file():
                    context = context_path.read_text(encoding="utf-8")[:20000]
                    break
        # visual_attachments alone still deserve an explicit ATTACHED listing
        if isinstance(visual_attachments, list) and visual_attachments and not design_section:
            design_section = _format_design_context_section(
                {},
                visual_attachments=visual_attachments,
            )

    attachments_section = _format_visual_attachments_section(request)
    allowed_paths = sanitize_allowed_paths(request.get("allowed_paths") or [])
    required_checks = [str(item) for item in request.get("required_checks") or []]
    return (
        f"{wu_summary}\n"
        f"Role: {role_id}. Procedure: {procedure_id}.\n"
        f"Resolved scope: {request.get('resolved_scope', [])}.\n"
        f"Allowed shell commands: {request.get('allowed_shell_commands', [])}.\n"
        f"Allowed paths: {allowed_paths}.\n"
        f"Required governed check names: {required_checks}.\n"
        f"{design_section}"
        f"{attachments_section}"
        f"Context package:\n{context}\n"
        "Execute only this governed step. Stay strictly "
        "within the declared scope. Never modify constitution, governance, "
        "or .ai-team/schemas files. Never modify .ai-team/work-units, "
        ".ai-team/state, .ai-team/runs, or authorization grants; only the "
        "Control Plane may update workflow status. Do not target staging or production. "
        "For implementation, leave a coherent Git commit. Return ONLY a JSON object "
        "with keys summary, checks, artifacts, requested_commands and usage. "
        "Each successful check must contain name, status='passed', and evidence_ref. "
        "Use every required governed check name exactly; AC-* checks may be added. "
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


def _run_state_stop_reason(path: Path) -> str | None:
    """Stop a native agent when its owning Run is no longer active."""
    try:
        run = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "owning Run became unreadable"
    if run.get("status") != "active":
        return f"owning Run is {run.get('status') or 'not active'}"
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


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop the agent process and any children spawned in its group."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                process.kill()
    except Exception:  # noqa: BLE001 - best-effort teardown
        try:
            process.kill()
        except OSError:
            pass


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
    """Run the CLI with a bounded watchdog that observes grant revocation."""
    process_env = _sanitized_process_env(accessible_secrets or [])
    process_env["GOVERNED_AI_UNATTENDED_RUN"] = "1"
    process_env["GOVERNED_AI_ALLOWED_SHELL_COMMANDS"] = json.dumps(allowed_shell_commands)
    process_env["GOVERNED_AI_ALLOWED_PATHS"] = json.dumps(
        sanitize_allowed_paths(allowed_paths)
    )
    process_env["CURSOR_PROJECT_DIR"] = str(project_root.resolve())
    process_env.update(telemetry_context or {})
    popen_kwargs: dict[str, Any] = {
        "cwd": str(project_root),
        "env": process_env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **popen_kwargs)
    deadline = time.monotonic() + timeout_seconds
    while True:
        reason = _kill_switch_reason(kill_switch_path)
        if reason is None and run_state_path is not None:
            reason = _run_state_stop_reason(run_state_path)
        if reason is not None:
            _terminate_process_tree(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process)
                process.communicate()
            return None, reason
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_process_tree(process)
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
