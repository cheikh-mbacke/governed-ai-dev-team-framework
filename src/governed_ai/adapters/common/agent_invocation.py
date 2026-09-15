"""Real native-CLI invocation machinery shared by every Adaptateur runtime.

Extracted from ``adapters/cursor/runtime/agent_cli.py`` — prompt assembly,
the governance watchdog (kill-switch / Run-state polling), sanitized
subprocess environment, and process-tree teardown have zero Cursor-specific
content; only the exact CLI binary name, its flags, and its JSON output
envelope are adapter-specific and stay local to each adapter's own
``*_cli.py``. ``run_agent_process``'s ``project_dir_env_var`` parameter is
the one seam that was hardcoded to ``CURSOR_PROJECT_DIR`` here — Claude
Code uses ``CLAUDE_PROJECT_DIR`` (see ``adapters/claude_code/runtime/
claude_cli.py``).
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.domain.run.path_policy import sanitize_allowed_paths

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


def git_head(project_root: Path) -> str | None:
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


def kill_switch_reason(path: Path) -> str | None:
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


def run_state_stop_reason(path: Path) -> str | None:
    """Stop a native agent when its owning Run is no longer active."""
    try:
        run = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "owning Run became unreadable"
    if run.get("status") != "active":
        return f"owning Run is {run.get('status') or 'not active'}"
    return None


def sanitized_process_env(accessible_secrets: list[str]) -> dict[str, str]:
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


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
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


def run_agent_process(
    command: list[str],
    *,
    project_root: Path,
    timeout_seconds: float,
    kill_switch_path: Path,
    allowed_shell_commands: list[str],
    allowed_paths: list[str],
    project_dir_env_var: str,
    accessible_secrets: list[str] | None = None,
    telemetry_context: dict[str, str] | None = None,
    run_state_path: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    """Run the CLI with a bounded watchdog that observes grant revocation.

    ``project_dir_env_var`` is the adapter-specific env var name used to tell
    the native tool (and its hooks) the project root — e.g.
    ``CURSOR_PROJECT_DIR`` or ``CLAUDE_PROJECT_DIR``.
    """
    process_env = sanitized_process_env(accessible_secrets or [])
    process_env["GOVERNED_AI_UNATTENDED_RUN"] = "1"
    process_env["GOVERNED_AI_ALLOWED_SHELL_COMMANDS"] = json.dumps(allowed_shell_commands)
    process_env["GOVERNED_AI_ALLOWED_PATHS"] = json.dumps(
        sanitize_allowed_paths(allowed_paths)
    )
    process_env[project_dir_env_var] = str(project_root.resolve())
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
        reason = kill_switch_reason(kill_switch_path)
        if reason is None and run_state_path is not None:
            reason = run_state_stop_reason(run_state_path)
        if reason is not None:
            terminate_process_tree(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                terminate_process_tree(process)
                process.communicate()
            return None, reason
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_process_tree(process)
            process.communicate()
            raise subprocess.TimeoutExpired(cmd=command, timeout=timeout_seconds)
        try:
            stdout, stderr = process.communicate(timeout=min(0.5, remaining))
        except subprocess.TimeoutExpired:
            continue
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr), None


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "ENABLE_ENV_VAR",
    "AgentInvocationOutcome",
    "build_prompt",
    "git_head",
    "is_real_agent_launch_enabled",
    "kill_switch_reason",
    "run_agent_process",
    "run_state_stop_reason",
    "sanitized_process_env",
    "terminate_process_tree",
]
