"""A single scheduling decision for one Run (orchestrator, first slice).

`run_scheduling_tick` takes exactly one action per call and returns what it
did — it never loops, sleeps, or blocks itself. The only part of this
feature that becomes a genuine long-running process is the thin CLI wrapper
in `scripts/ai-team/orchestrate.py`, which is deliberately not covered by
unit tests: real wall-clock behavior is not something a unit test can prove
(see docs/framework-design/requirements/mode-nuit-preuve-resilience-couverture.md).

Every write goes through `CommandGateway.execute_command()` like any other
caller — this module has no special access and cannot bypass fencing,
execution_ceiling, convergence bounds, or grant checks.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from governed_ai.adapters.spi import AdapterSPI, ExecutionRequest
from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.run.autonomy_policy import (
    effective_policy_hash,
    is_unattended_preset,
    resolve_step_timeout_seconds,
)
from governed_ai.core.domain.run.convergence import (
    DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP,
    DEFAULT_MAXIMUM_REMEDIATION_CYCLES,
    convergence_exhaustion_reason,
)
from governed_ai.core.domain.run.failure_taxonomy import (
    classify_attempt_failure,
    systemic_failure_signature,
)
from governed_ai.core.domain.run.mission_artifact import compute_artifact_hash
from governed_ai.core.domain.run.path_policy import sanitize_allowed_paths
from governed_ai.core.orchestrator.boundary import boundary_error_for_changed_files
from governed_ai.core.orchestrator.context_package import (
    completeness_error,
    evaluate_context_package_completeness,
)
from governed_ai.core.orchestrator.git_workspace import (
    GitWorkspaceError,
    changed_files,
    create_unverified_wip_commit,
    ensure_integration_worktree,
    ensure_work_unit_worktree,
    head_sha,
    list_uncommitted_files,
    merge_and_revalidate,
)
from governed_ai.core.orchestrator.progress import evaluate_run_progress
from governed_ai.core.workspace import Workspace
from governed_ai.feedback.domain.auto_observation import classify_auto_observation

# Document 6 §9.3 / orchestrator.json — which dispatch step corresponds to a
# Work Unit's current status, where a *succeeded* attempt at that step
# advances it, and where a convergence-exhausted attempt demotes it.
# Deliberately stops at "human_test": the human_test → done transition
# requires human acceptance (domain/work_unit/done.py) and is never
# something this loop decides on its own (Document 6 §2.1/§2.2).
STATUS_TO_STEP = {
    "in_progress": "sandbox_implementation",
    "verification": "verification",
    "review": "review",
    "audit": "audit",
    "remediation_required": "remediation",
}
NEXT_STATUS_ON_SUCCESS = {
    "in_progress": "verification",
    "verification": "review",
    "review": "audit",
    "audit": "human_test",
    "remediation_required": "verification",
}
NEXT_STATUS_ON_EXHAUSTION = {
    "in_progress": "blocked",
    "verification": "remediation_required",
    "review": "remediation_required",
    "audit": "remediation_required",
    "remediation_required": "blocked",
}

# The orchestrator acts as control-plane executing the pre-existing
# "orchestrator" procedure (src/governed_ai/contracts/bundles/v1/procedures/
# orchestrator.json) — the one already in control-plane's procedure_refs
# describing this exact loop, not a role/procedure invented for this file.
DISPATCH_CONTRACTS = {
    "sandbox_implementation": ("backend-developer", "implement-work-unit", ("implementation",)),
    "remediation": ("backend-developer", "implement-work-unit", ("implementation",)),
    "verification": ("qa-test", "webapp-testing", ("tests",)),
    "review": ("code-reviewer", "webapp-testing", ("code_review",)),
    "security_review": ("security-reviewer", "security-review", ("security_review",)),
    "audit": ("auditor", "audit-release", ("audit",)),
    "integration_review": (
        "integration-steward",
        "integrate-work-units",
        ("integration_review",),
    ),
}

IMPLEMENTATION_ROLES = frozenset({"backend-developer", "frontend-developer"})


def _resolve_execution_contract(
    workspace: Workspace, *, role_id: str, procedure_id: str
) -> dict[str, str]:
    """Read real bundle/role/procedure identities so a real AdapterSPI can
    negotiate compatibility instead of crashing on a missing `contract`."""
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    role = json.loads((bundle_dir / "roles" / f"{role_id}.json").read_text(encoding="utf-8"))
    procedure = json.loads(
        (bundle_dir / "procedures" / f"{procedure_id}.json").read_text(encoding="utf-8")
    )
    return {
        "bundle_version": manifest["bundle_version"],
        "bundle_hash": manifest["content_hash"],
        "role_id": role["role_id"],
        "role_revision": role["revision"],
        "procedure_id": procedure["procedure_id"],
        "procedure_revision": procedure["revision"],
    }


_MAX_AUTO_SYMPTOM = 2000


def _procedure_required_inputs(workspace: Workspace, procedure_id: str) -> list[str]:
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
    procedure = json.loads(
        (bundle_dir / "procedures" / f"{procedure_id}.json").read_text(encoding="utf-8")
    )
    return [str(item) for item in (procedure.get("required_inputs") or [])]


_CONTEXT_PACKAGES_REL = ".ai-team/context-packages"


def _canonical_context_package_path(workspace: Workspace, ref: str) -> Path:
    """Resolve a context package ref strictly under ``.ai-team/context-packages/``."""
    text = str(ref).strip().replace("\\", "/")
    if not text:
        raise ValueError("empty context_package_ref")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ValueError("context_package_ref must be a relative id under context-packages")
    parts = Path(text).parts
    if ".." in parts:
        raise ValueError("context_package_ref must not contain '..'")

    packages_root = (workspace.ai_team / "context-packages").resolve()
    if text.endswith(".yaml"):
        if text.startswith(f"{_CONTEXT_PACKAGES_REL}/"):
            candidate = (workspace.root / text).resolve()
        elif "/" in text or text.startswith("."):
            raise ValueError(
                "context_package_ref path must be "
                f"{_CONTEXT_PACKAGES_REL}/<id>.yaml or a bare package id"
            )
        else:
            candidate = (packages_root / text).resolve()
    else:
        if "/" in text or text.startswith("."):
            raise ValueError("context_package_ref id must not contain path separators")
        candidate = (packages_root / f"{text}.yaml").resolve()

    try:
        candidate.relative_to(packages_root)
    except ValueError as exc:
        raise ValueError(
            "context_package_ref escapes .ai-team/context-packages/"
        ) from exc
    return candidate


def _resolve_context_package_ref(
    workspace: Workspace,
    wu_document: dict[str, Any],
    *,
    procedure_id: str,
    role_id: str,
) -> tuple[str | None, str | None]:
    """Return (request-relative path, error). Error set when context is required but unusable."""
    from jsonschema import Draft202012Validator, FormatChecker

    from governed_ai.core.persistence.io import load_json

    required = _procedure_required_inputs(workspace, procedure_id)
    needs_context = "context_package" in required
    raw_ref = wu_document.get("context_package_ref")
    if raw_ref in (None, ""):
        if needs_context:
            return None, "context_package required but work unit has no context_package_ref"
        return None, None
    try:
        path = _canonical_context_package_path(workspace, str(raw_ref))
    except ValueError as exc:
        if needs_context:
            return None, str(exc)
        return None, None
    if not path.is_file():
        if needs_context:
            try:
                display = path.relative_to(workspace.root).as_posix()
            except ValueError:
                display = str(path)
            return None, f"context_package missing or unreadable: {display}"
        return None, None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        if needs_context:
            return None, f"context_package invalid: {exc}"
        return None, None
    if not isinstance(document, dict):
        if needs_context:
            return None, "context_package invalid: document must be a mapping"
        return None, None

    schema_path = workspace.ai_team / "schemas" / "context-package.schema.json"
    try:
        schema = load_json(schema_path)
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                document
            ),
            key=lambda error: list(error.path),
        )
    except (OSError, ValueError, TypeError) as exc:
        if needs_context:
            return None, f"context_package schema unavailable: {exc}"
        return None, None
    if errors:
        first = errors[0]
        pointer = "/" + "/".join(str(part) for part in first.path) if first.path else "/"
        message = f"context_package schema invalid at {pointer}: {first.message}"
        if needs_context:
            return None, message
        return None, None

    expected_id = path.stem
    if str(document.get("id") or "") != expected_id:
        message = (
            f"context_package id {document.get('id')!r} does not match "
            f"requested package id {expected_id!r}"
        )
        if needs_context:
            return None, message
        return None, None

    work_unit_id = str(wu_document.get("id") or "")
    if str(document.get("work_unit") or "") != work_unit_id:
        message = (
            f"context_package work_unit {document.get('work_unit')!r} "
            f"does not match work unit {work_unit_id!r}"
        )
        if needs_context:
            return None, message
        return None, None
    if str(document.get("role") or "") != str(role_id):
        message = (
            f"context_package role {document.get('role')!r} "
            f"does not match dispatched role {role_id!r}"
        )
        if needs_context:
            return None, message
        return None, None

    if needs_context:
        evaluation = evaluate_context_package_completeness(
            workspace_root=workspace.root,
            context_document=document,
            context_path=path,
            wu_document=wu_document,
        )
        error = completeness_error(evaluation)
        if error:
            return None, error
    return path.relative_to(workspace.root).as_posix(), None


def _role_candidates(value: Any) -> list[str]:
    """Extract explicit implementation roles from flexible staffing payloads."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [candidate for item in value for candidate in _role_candidates(item)]
    if isinstance(value, dict):
        preferred_keys = (
            "role",
            "role_id",
            "primary_role",
            "implementer",
            "assigned_role",
        )
        preferred = [
            candidate
            for key in preferred_keys
            if key in value
            for candidate in _role_candidates(value[key])
        ]
        remaining = [
            candidate
            for key, item in value.items()
            if key not in preferred_keys
            for candidate in _role_candidates(item)
        ]
        return preferred + remaining
    return []


def _context_package_role(workspace: Workspace, work_unit: dict[str, Any]) -> str | None:
    ref = work_unit.get("context_package_ref")
    if not ref:
        return None
    try:
        document = _read_yaml(_canonical_context_package_path(workspace, str(ref))) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return None
    role = str(document.get("role") or "").strip()
    return role if role in IMPLEMENTATION_ROLES else None


def _resolve_implementation_role(
    workspace: Workspace, work_unit: dict[str, Any]
) -> str:
    """Resolve implementer from staffing, compiled context, then touched area."""
    for source in (work_unit.get("staffing_proposal"), work_unit.get("staffing")):
        for candidate in _role_candidates(source):
            if candidate in IMPLEMENTATION_ROLES:
                return candidate

    context_role = _context_package_role(workspace, work_unit)
    if context_role is not None:
        return context_role

    area = str((work_unit.get("zone") or {}).get("area") or "").lower()
    if area in {"frontend", "mobile"}:
        return "frontend-developer"
    return "backend-developer"


def _adapter_identity(adapter: Any) -> dict[str, str]:
    """Read adapter identity from SPI self-description, failing closed."""
    describe = getattr(adapter, "describe", None)
    if not callable(describe):
        return {"id": "external", "version": "unknown"}
    try:
        descriptor = describe()
    except Exception:  # noqa: BLE001 - descriptor probing must not invent identity
        return {"id": "external", "version": "unknown"}
    if not isinstance(descriptor, dict):
        return {"id": "external", "version": "unknown"}
    return {
        "id": str(descriptor.get("adapter_id") or "external"),
        "version": str(descriptor.get("adapter_version") or "unknown"),
    }


@dataclass(frozen=True, slots=True)
class TickResult:
    action: str
    work_unit_id: str | None
    details: dict[str, Any] = field(default_factory=dict)


def _lease_is_fresh(lease: dict[str, Any], *, now: datetime) -> bool:
    heartbeat_at = lease.get("heartbeat_at")
    stalled_after_minutes = lease.get("stalled_after_minutes", 15)
    if not heartbeat_at:
        return False
    heartbeat = datetime.fromisoformat(heartbeat_at)
    return now - heartbeat < timedelta(minutes=stalled_after_minutes)


def _actor(role_id: str = "control-plane") -> dict[str, Any]:
    return {
        "kind": "role",
        "execution_id": f"EXE-orchestrator-{uuid.uuid4().hex[:8]}",
        "role_id": role_id,
        "bundle_version": "1.0.0",
        "adapter_id": "core-orchestrator",
    }


def _envelope(
    command_type: str,
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    actor_role_id: str = "control-plane",
) -> dict[str, Any]:
    key = f"orchestrator-{uuid.uuid4().hex}"
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-{key}",
        "idempotency_key": f"idem-{key}",
        "correlation_id": key,
        "type": command_type,
        "issued_at": datetime.now(UTC).isoformat(),
        "actor": _actor(actor_role_id),
        "target": target,
        "payload": payload,
    }


def _best_effort_submit_feedback(gateway: CommandGateway) -> dict[str, Any]:
    """ADR-009 remount after Run terminal close — never blocks scheduling."""
    submit_receipt, submit_exit = gateway.execute_command(
        _envelope(
            "SubmitFeedback",
            target={"kind": "feedback_export", "id": "new"},
            payload={},
        )
    )
    if submit_exit == 0:
        affected = (submit_receipt.get("affected") or [{}])[0]
        return {
            "feedback_submit": {
                "path": affected.get("path"),
                "transmission_status": affected.get("transmission_status"),
            }
        }
    return {"feedback_submit_errors": submit_receipt.get("errors")}


def _terminal_run_result(
    gateway: CommandGateway,
    *,
    close_exit: int,
    action_ok: str,
    action_fail: str,
    work_unit_id: str | None,
    details: dict[str, Any],
) -> TickResult:
    merged = dict(details)
    if close_exit == 0:
        merged.update(_best_effort_submit_feedback(gateway))
        return TickResult(action=action_ok, work_unit_id=work_unit_id, details=merged)
    return TickResult(action=action_fail, work_unit_id=work_unit_id, details=merged)


def _read_yaml(path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return yaml.safe_load(_read_text(path))


def _read_text(path) -> str:
    for attempt in range(200):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == 199:
                raise
            time.sleep(0.01)
    raise AssertionError("unreachable")


def _git_head(workspace: Workspace) -> str | None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.root}", "rev-parse", "HEAD"],
        cwd=str(workspace.root),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    value = completed.stdout.strip().lower()
    return value if completed.returncode == 0 and len(value) == 40 else None


def _integration_verification_command(workspace: Workspace) -> str:
    profile = _read_yaml(workspace.ai_team / "project-profile.yaml") or {}
    commands = profile.get("commands") or {}
    command = commands.get("integration_test") or commands.get("unit_test")
    if not command:
        raise GitWorkspaceError(
            "project-profile.yaml must define commands.integration_test or commands.unit_test"
        )
    return str(command)


def _integration_conflict_attempts(
    workspace: Workspace, run_id: str, work_unit_id: str
) -> int:
    return sum(
        1
        for item in _attempts_for_work_unit(workspace, run_id, work_unit_id)
        if item.get("step") == "integration_review" and item.get("status") != "succeeded"
    )


def _attempts_for_work_unit(workspace: Workspace, run_id: str, work_unit_id: str) -> list[dict[str, Any]]:
    directory = workspace.ai_team / "runs" / "execution-attempts"
    if not directory.is_dir():
        return []
    attempts = []
    for path in sorted(directory.glob("*.yaml")):
        item = _read_yaml(path)
        if item and item.get("run_id") == run_id and item.get("work_unit_id") == work_unit_id:
            attempts.append(item)
    return attempts


def _dispatch_step(workspace: Workspace, run_id: str, work_unit_id: str, status: str) -> str | None:
    if status != "audit":
        return STATUS_TO_STEP.get(status)
    attempts = _attempts_for_work_unit(workspace, run_id, work_unit_id)
    security_done = any(
        item.get("step") == "security_review" and item.get("status") == "succeeded"
        for item in attempts
    )
    if not security_done:
        return "security_review"
    audit_done = any(
        item.get("step") == "audit" and item.get("status") == "succeeded"
        for item in attempts
    )
    if not audit_done:
        return "audit"
    run_document = _read_yaml(workspace.ai_team / "runs" / f"{run_id}.yaml") or {}
    if run_document.get("autonomy_preset") in {
        "unattended_extended",
        "unattended_maximal",
        "custom",
    }:
        return "integration_review"
    return "audit"


def _pre_dispatch_exhaustion_reason(
    workspace: Workspace,
    run_document: dict[str, Any],
    *,
    work_unit_id: str,
    step: str,
) -> str | None:
    attempts = [
        item
        for item in _attempts_for_work_unit(workspace, str(run_document["id"]), work_unit_id)
        if item.get("step") == step
    ]
    return convergence_exhaustion_reason(
        attempts,
        step=step,
        maximum_attempts_per_step=int(
            run_document.get(
                "maximum_attempts_per_step", DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP
            )
        ),
        maximum_remediation_cycles=int(
            run_document.get(
                "maximum_remediation_cycles", DEFAULT_MAXIMUM_REMEDIATION_CYCLES
            )
        ),
    )


def _explicit_acceptance_criterion_ids(work_unit: dict[str, Any] | None) -> tuple[str, ...]:
    """Return AC-* identifiers declared on the Work Unit, when present."""
    if not work_unit:
        return ()
    ids: list[str] = []
    for item in work_unit.get("acceptance_criteria") or []:
        if isinstance(item, dict) and len(item) == 1:
            key = str(next(iter(item))).strip()
            if key.startswith("AC-"):
                ids.append(key)
            continue
        if isinstance(item, str):
            token = item.strip().split()[0] if item.strip() else ""
            token = token.split(":", 1)[0].strip()
            if token.startswith("AC-"):
                ids.append(token)
    return tuple(ids)


def _expanded_ac_ranges(check_names: set[str]) -> set[str]:
    expanded: set[str] = set()
    for name in check_names:
        match = re.match(r"^(AC-.+-)(\d+)\.\.(\d+)(?:\D|$)", name)
        if not match:
            continue
        prefix, start_text, end_text = match.groups()
        start, end = int(start_text), int(end_text)
        if end < start or end - start > 100:
            continue
        width = max(len(start_text), len(end_text))
        expanded.update(f"{prefix}{index:0{width}d}" for index in range(start, end + 1))
    return expanded


def _covered_acceptance_criteria(ac_ids: tuple[str, ...], passed: set[str]) -> set[str]:
    expanded = _expanded_ac_ranges(passed)
    covered: set[str] = set()
    for ac_id in ac_ids:
        if ac_id in expanded or any(
            name == ac_id
            or (name.startswith(ac_id) and name[len(ac_id) : len(ac_id) + 1] in " :_-./")
            for name in passed
        ):
            covered.add(ac_id)
    return covered


def _check_matches_required(name: str, required: str) -> bool:
    """Normalize agent check names via the canonical registry (no fuzzy substrings)."""
    from governed_ai.core.execution_gateway.check_registry import normalize_check_name

    canonical = normalize_check_name(name)
    if canonical is None:
        return False
    wanted = normalize_check_name(required) or required
    return canonical == wanted


def _evidence_error(
    result: dict[str, Any],
    *,
    required_checks: tuple[str, ...],
    require_changed_sha: bool,
    base_sha: str | None,
    work_unit: dict[str, Any] | None = None,
) -> str | None:
    checks = result.get("checks") or []
    passed = {
        str(item.get("name"))
        for item in checks
        if item.get("name") and item.get("status") == "passed" and item.get("evidence_ref")
    }
    if require_changed_sha:
        # Implementation / remediation: transport check "implementation" is optional
        # when explicit AC-* checks (with evidence_ref) cover the Work Unit.
        ac_ids = _explicit_acceptance_criterion_ids(work_unit)
        ac_passed = {name for name in passed if name.startswith("AC-")}
        has_implementation = "implementation" in passed
        if ac_ids:
            missing_acs = sorted(set(ac_ids) - _covered_acceptance_criteria(ac_ids, passed))
            ac_ok = not missing_acs
        else:
            missing_acs = []
            ac_ok = bool(ac_passed)
        if not has_implementation and not ac_ok:
            if ac_ids:
                return (
                    "missing passed checks with evidence: "
                    f"{missing_acs} (or check name 'implementation')"
                )
            return "missing passed checks with evidence: ['implementation'] or AC-* with evidence_ref"
        result_sha = (result.get("workspace") or {}).get("result_sha")
        if not result_sha or result_sha == base_sha:
            return "implementation did not produce a new coherent commit SHA"
        if not result.get("artifacts"):
            return "implementation produced no hashed artifact"
        return None

    missing = sorted(
        required
        for required in required_checks
        if not any(_check_matches_required(name, required) for name in passed)
    )
    if missing == ["tests"]:
        ac_ids = _explicit_acceptance_criterion_ids(work_unit)
        if ac_ids and set(ac_ids) == _covered_acceptance_criteria(ac_ids, passed):
            missing = []
    if missing:
        return f"missing passed checks with evidence: {missing}"
    return None


def _release_lease(
    gateway: CommandGateway,
    *,
    run_id: str,
    work_unit_id: str,
    lease_ref: dict[str, Any],
    reason: str,
) -> tuple[dict[str, Any], int]:
    return gateway.execute_command(
        _envelope(
            "ReleaseWorkerLease",
            target={"kind": "worker_lease", "id": lease_ref["lease_id"]},
            payload={
                "run_id": run_id,
                "work_unit_id": work_unit_id,
                "epoch": lease_ref["epoch"],
                "reason": reason,
            },
        )
    )


def _dependencies_satisfied(
    work_unit: dict[str, Any], work_unit_documents: dict[str, dict[str, Any] | None]
) -> bool:
    for dependency in work_unit.get("dependencies") or []:
        dependency_id = dependency if isinstance(dependency, str) else dependency.get("id")
        if not dependency_id:
            continue
        dependency_document = work_unit_documents.get(dependency_id)
        if dependency_document is None or dependency_document.get("status") not in {
            "human_test",
            "done",
        }:
            return False
    return True


def _all_work_units_ready_for_morning_review(
    work_unit_ids: list[str],
    work_unit_documents: dict[str, dict[str, Any] | None],
) -> bool:
    return bool(work_unit_ids) and all(
        (work_unit_documents.get(work_unit_id) or {}).get("status") in {"human_test", "done"}
        for work_unit_id in work_unit_ids
    )


def _global_stop_condition(
    workspace: Workspace, run_document: dict[str, Any], *, now: datetime
) -> str | None:
    grant_id = run_document.get("run_authorization_grant_id")
    if not grant_id:
        return "state_corruption"
    for work_unit_id in run_document.get("work_unit_ids") or []:
        if not (workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").is_file():
            return "state_corruption"
    grant_path = workspace.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if not grant_path.is_file():
        return "state_corruption"
    try:
        grant = json.loads(_read_text(grant_path))
    except (OSError, json.JSONDecodeError):
        return "state_corruption"
    policy = run_document.get("effective_autonomy_policy")
    if policy is not None:
        expected_policy_hash = effective_policy_hash(policy)
        if (
            run_document.get("effective_autonomy_policy_hash") != expected_policy_hash
            or grant.get("effective_autonomy_policy_hash") != expected_policy_hash
        ):
            return "state_corruption"
    for artifact_id, expected_hash in (grant.get("mission_artifact_hashes") or {}).items():
        artifact_path = workspace.ai_team / "mission-artifacts" / f"{artifact_id}.json"
        try:
            artifact = json.loads(_read_text(artifact_path))
        except (OSError, json.JSONDecodeError):
            return "state_corruption"
        if compute_artifact_hash(artifact) != expected_hash:
            return "state_corruption"
    active_by_work_unit: dict[str, list[str]] = {}
    leases_dir = workspace.ai_team / "runs" / "leases"
    if leases_dir.is_dir():
        for lease_path in leases_dir.glob("*.yaml"):
            try:
                lease = _read_yaml(lease_path) or {}
            except (OSError, yaml.YAMLError):
                return "state_corruption"
            if lease.get("run_id") == run_document.get("id") and lease.get("status") == "active":
                active_by_work_unit.setdefault(str(lease.get("work_unit_id")), []).append(
                    str(lease.get("id"))
                )
    if any(len(ids) > 1 for ids in active_by_work_unit.values()):
        return "fencing_conflict"
    if set(active_by_work_unit) != set(run_document.get("leases_by_work_unit") or {}):
        return "fencing_conflict"
    for work_unit_id, lease_ref in (run_document.get("leases_by_work_unit") or {}).items():
        if active_by_work_unit.get(work_unit_id) != [str(lease_ref.get("lease_id"))]:
            return "fencing_conflict"
    if grant.get("revoked_at"):
        return "kill_switch"
    expires_at = grant.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
        except ValueError:
            return "state_corruption"
        if now >= expiry:
            return "authorization_violation"
    duration = grant.get("maximum_duration_hours")
    if duration is not None and run_document.get("created_at"):
        opened = datetime.fromisoformat(str(run_document["created_at"]).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
        if (now - opened).total_seconds() >= float(duration) * 3600:
            return "budget_exhausted"
    maximum_spend = grant.get("maximum_spend")
    if maximum_spend is not None and float(grant.get("spend_used", 0)) >= float(maximum_spend):
        return "budget_exhausted"
    maximum_tokens = grant.get("maximum_tokens")
    if maximum_tokens is not None and int(grant.get("tokens_used", 0)) >= int(maximum_tokens):
        return "budget_exhausted"
    progress = evaluate_run_progress(workspace.ai_team, run_document, now=now)
    if progress["state"] == "stalled_no_progress":
        return "stalled_no_progress"
    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    failures: dict[tuple[str, ...], set[str]] = {}
    if attempts_dir.is_dir():
        for path in attempts_dir.glob("*.yaml"):
            attempt = _read_yaml(path) or {}
            if attempt.get("run_id") != run_document.get("id"):
                continue
            signature = systemic_failure_signature(attempt)
            if signature is None:
                continue
            failures.setdefault(signature, set()).add(str(attempt.get("work_unit_id")))
    if any(len(work_units) >= 2 for work_units in failures.values()):
        return "repeated_systemic_failure"
    return None


def _execution_envelope_constraints(
    workspace: Workspace, run_document: dict[str, Any]
) -> tuple[list[str], list[str] | None, list[str]]:
    """Return (shell_commands, allowed_paths|None, secrets).

    ``allowed_paths is None`` means the grant does not constrain paths (axis absent).
    An explicit empty list means the grant forbids all product writes.
    """
    grant_id = run_document.get("run_authorization_grant_id")
    if not grant_id:
        return [], None, []
    grant_path = workspace.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if not grant_path.is_file():
        return [], None, []
    grant = json.loads(_read_text(grant_path))
    if "allowed_paths" in grant:
        allowed_paths: list[str] | None = sanitize_allowed_paths(grant.get("allowed_paths") or [])
    else:
        allowed_paths = None
    return (
        [str(item) for item in grant.get("allowed_shell_commands") or []],
        allowed_paths,
        [str(item) for item in grant.get("accessible_secrets") or []],
    )


def _implementation_boundary_error(
    *,
    execution_root,
    base_sha: str | None,
    result: dict[str, Any],
    wu_document: dict[str, Any],
    run_document: dict[str, Any],
    allowed_paths: list[str],
) -> tuple[str, str | None] | None:
    """Return (message, global_stop_condition) for a boundary violation, else None.

    Document 6 §9.5 — a write outside the authorized workspace (product scope /
    envelope, or protected governance paths) is one of the fixed conditions that
    stops the whole Run, not just this Work Unit. Narrow Work-Unit governed
    outputs such as ``.ai-team/evidence/<WU>/**`` are allowed separately and do
    not relax product scope.
    """
    if base_sha is None:
        return "isolated implementation workspace has no base commit", None
    try:
        actual_sha = head_sha(execution_root)
    except GitWorkspaceError as exc:
        return f"cannot verify worker Git result: {exc}", None
    claimed_sha = (result.get("workspace") or {}).get("result_sha")
    if claimed_sha != actual_sha:
        return f"claimed result SHA {claimed_sha!r} does not match worker HEAD {actual_sha!r}", None
    try:
        files = changed_files(execution_root, base_sha, actual_sha)
    except GitWorkspaceError as exc:
        return f"cannot inspect worker diff: {exc}", None

    work_unit_id = str(wu_document.get("id") or "")
    classification_error = boundary_error_for_changed_files(
        files,
        work_unit_id=work_unit_id,
        wu_document=wu_document,
        allowed_paths=allowed_paths,
    )
    if classification_error:
        return classification_error

    policy_budgets = (run_document.get("effective_autonomy_policy") or {}).get("budgets") or {}
    maximum = int(policy_budgets.get("maximum_changed_files_per_work_unit", 30))
    if (wu_document.get("risk") or {}).get("class") == "critical":
        maximum = int(policy_budgets.get("maximum_changed_files_per_critical_work_unit", 10))
    if len(files) > maximum:
        return f"changed-file budget exceeded ({len(files)} > {maximum})", None
    dependency_files = {
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "go.mod",
        "go.sum",
        "cargo.toml",
        "cargo.lock",
    }
    maximum_dependencies = int(policy_budgets.get("maximum_new_dependencies", 0))
    touched_dependency_files = [
        path for path in files if path.rsplit("/", 1)[-1].lower() in dependency_files
    ]
    if maximum_dependencies == 0 and touched_dependency_files:
        return f"dependency changes are forbidden: {touched_dependency_files}", None
    return None


def _checkpoint_start_sha(workspace: Workspace, work_unit_id: str) -> str | None:
    path = workspace.ai_team / "runs" / "checkpoints" / f"{work_unit_id}.yaml"
    document = _read_yaml(path)
    if not document:
        return None
    sha = document.get("last_commit")
    if isinstance(sha, str) and len(sha) == 40:
        return sha.lower()
    return None


def _grant_remaining_seconds(
    workspace: Workspace, run_document: dict[str, Any], *, now: datetime
) -> float | None:
    grant_id = run_document.get("run_authorization_grant_id")
    if not grant_id:
        return None
    grant_path = workspace.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if not grant_path.is_file():
        return None
    try:
        grant = json.loads(_read_text(grant_path))
    except (OSError, json.JSONDecodeError):
        return None
    remaining: list[float] = []
    expires_at = grant.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            remaining.append(max(1.0, (expiry - now).total_seconds()))
        except ValueError:
            pass
    duration = grant.get("maximum_duration_hours")
    if duration is not None and run_document.get("created_at"):
        opened = datetime.fromisoformat(str(run_document["created_at"]).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
        remaining.append(max(1.0, float(duration) * 3600 - (now - opened).total_seconds()))
    if not remaining:
        return None
    return min(remaining)


def _recover_orphan_started_attempts(
    gateway: CommandGateway,
    workspace: Workspace,
    *,
    run_id: str,
    run_document: dict[str, Any],
    now: datetime,
) -> list[str]:
    """Finalize started attempts whose lease is gone or stale."""
    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    if not attempts_dir.is_dir():
        return []
    recovered: list[str] = []
    leases_by_work_unit = run_document.get("leases_by_work_unit") or {}
    for path in sorted(attempts_dir.glob("*.yaml")):
        attempt = _read_yaml(path) or {}
        if attempt.get("run_id") != run_id or attempt.get("status") != "started":
            continue
        work_unit_id = str(attempt.get("work_unit_id") or "")
        lease_id = str(attempt.get("worker_lease_id") or "")
        lease_path = workspace.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
        lease = _read_yaml(lease_path) if lease_path.is_file() else None
        current = leases_by_work_unit.get(work_unit_id) or {}
        lease_authoritative = (
            lease is not None
            and lease.get("status") == "active"
            and str(current.get("lease_id") or "") == lease_id
            and int(current.get("epoch") or 0) == int(attempt.get("epoch") or 0)
        )
        if lease_authoritative and _lease_is_fresh(lease, now=now):
            continue
        taxonomy = classify_attempt_failure(
            status="timed_out",
            step=str(attempt.get("step") or ""),
            summary="orphan started attempt recovered on restart",
        ) or {}
        payload = {
            "run_id": run_id,
            "execution_id": attempt.get("execution_id"),
            "work_unit_id": work_unit_id,
            "worker_lease_id": lease_id,
            "epoch": attempt.get("epoch") or 1,
            "step": attempt.get("step") or "sandbox_implementation",
            "status": "timed_out",
            "summary": "orphan started attempt recovered on restart",
            "checks": [],
            "artifacts": [],
            "workspace": attempt.get("workspace") or {},
            "contract": attempt.get("contract") or {},
            "requested_commands": [],
            "usage": {},
            "provider": {},
            **taxonomy,
        }
        if not lease_authoritative:
            payload["orphan_recovery"] = True
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "RecordExecutionAttempt",
                target={
                    "kind": "execution_attempt",
                    "id": attempt["id"],
                    "expected_revision": attempt.get("revision", 1),
                },
                payload=payload,
                actor_role_id="control-plane",
            )
        )
        if exit_code == 0:
            recovered.append(str(attempt["id"]))
        else:
            _ = receipt
    return recovered


_MACHINE_DISPATCHABLE_STATUSES = frozenset(
    {
        "ready",
        "in_progress",
        "verification",
        "review",
        "security_review",
        "audit",
        "remediation_required",
        "integration_review",
    }
)
_HUMAN_WAIT_STATUSES = frozenset(
    {
        "human_test",
        "paused_for_risk_escalation",
    }
)


def _run_has_dispatchable_work(
    workspace: Workspace,
    run_document: dict[str, Any],
    work_unit_documents: dict[str, dict[str, Any] | None],
    *,
    now: datetime,
) -> bool:
    """True when a future tick could still acquire or dispatch machine work."""
    for _work_unit_id, wu_document in work_unit_documents.items():
        if wu_document is None:
            continue
        status = wu_document.get("status")
        if status in _MACHINE_DISPATCHABLE_STATUSES or status in STATUS_TO_STEP:
            return True
    leases_dir = workspace.ai_team / "runs" / "leases"
    if leases_dir.is_dir():
        for lease_path in leases_dir.glob("*.yaml"):
            lease = _read_yaml(lease_path) or {}
            if (
                lease.get("run_id") == run_document.get("id")
                and lease.get("status") == "active"
                and _lease_is_fresh(lease, now=now)
            ):
                return True
    return False


def _run_awaits_human(
    work_unit_documents: dict[str, dict[str, Any] | None],
) -> bool:
    return any(
        (document or {}).get("status") in _HUMAN_WAIT_STATUSES
        for document in work_unit_documents.values()
        if document is not None
    )


def _should_stop_for_no_dispatchable_work(
    work_unit_documents: dict[str, dict[str, Any] | None],
) -> bool:
    """Close when remaining work is stuck and nothing awaits a human gate."""
    statuses = [
        str((document or {}).get("status") or "")
        for document in work_unit_documents.values()
        if document is not None
    ]
    if not statuses:
        return True
    if any(status in _MACHINE_DISPATCHABLE_STATUSES or status in STATUS_TO_STEP for status in statuses):
        return False
    if any(status in _HUMAN_WAIT_STATUSES for status in statuses):
        return False
    if all(status == "done" for status in statuses):
        return False
    # Stuck statuses (blocked, …), optionally mixed with done.
    return True


def run_scheduling_tick(
    gateway: CommandGateway,
    workspace: Workspace,
    *,
    run_id: str,
    adapter: AdapterSPI,
    worker_id: str,
) -> TickResult:
    run_path = workspace.ai_team / "runs" / f"{run_id}.yaml"
    run_document = _read_yaml(run_path)
    if run_document is None:
        raise FileNotFoundError(f"run {run_id!r} not found at {run_path}")
    if run_document.get("status") != "active":
        return TickResult(
            action="run_not_active",
            work_unit_id=None,
            details={"status": run_document.get("status")},
        )

    now = datetime.now(UTC)
    stop_condition = _global_stop_condition(workspace, run_document, now=now)
    if stop_condition:
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "CloseRun",
                target={
                    "kind": "run",
                    "id": run_id,
                    "expected_revision": run_document["revision"],
                },
                payload={
                    "status": "stopped",
                    "reason": f"run-reliability-controller: {stop_condition}",
                    "stop_condition": stop_condition,
                },
            )
        )
        return _terminal_run_result(
            gateway,
            close_exit=exit_code,
            action_ok="run_stopped",
            action_fail="run_stop_failed",
            work_unit_id=None,
            details={"stop_condition": stop_condition, "errors": receipt.get("errors")},
        )
    work_unit_ids: list[str] = run_document.get("work_unit_ids") or []
    leases_by_work_unit: dict[str, dict[str, Any]] = run_document.get("leases_by_work_unit") or {}

    work_unit_documents: dict[str, dict[str, Any] | None] = {
        work_unit_id: _read_yaml(workspace.ai_team / "work-units" / f"{work_unit_id}.yaml")
        for work_unit_id in work_unit_ids
    }

    recovered_orphans = _recover_orphan_started_attempts(
        gateway,
        workspace,
        run_id=run_id,
        run_document=run_document,
        now=now,
    )
    if recovered_orphans:
        # Re-load run after authoritative attempt updates (budgets / events).
        run_document = _read_yaml(run_path) or run_document

    # Priority 1: reassign any stale lease before anything else.
    for work_unit_id, lease_ref in leases_by_work_unit.items():
        lease_document = _read_yaml(
            workspace.ai_team / "runs" / "leases" / f"{lease_ref['lease_id']}.yaml"
        )
        if lease_document is None or lease_document.get("status") != "active":
            continue
        if _lease_is_fresh(lease_document, now=now):
            continue
        new_lease_id = f"LEASE-{work_unit_id}-{uuid.uuid4().hex[:8]}"
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "AcquireWorkerLease",
                target={"kind": "worker_lease", "id": new_lease_id},
                payload={
                    "id": new_lease_id,
                    "run_id": run_id,
                    "work_unit_id": work_unit_id,
                    "worker_id": worker_id,
                },
            )
        )
        if exit_code != 0:
            return TickResult(
                action="reassignment_failed",
                work_unit_id=work_unit_id,
                details={"errors": receipt.get("errors")},
            )
        return TickResult(
            action="reassigned_lease", work_unit_id=work_unit_id, details={"lease_id": new_lease_id}
        )

    # Priority 2: start a ready Work Unit that has no lease at all yet.
    # Acquire the lease *before* transitioning the Work Unit's own status:
    # AcquireWorkerLease is the one that can be rejected by the parallelism
    # cap (Document 6 §11), and it does not care what the Work Unit's status
    # is. Doing it first means a rejected lease leaves the Work Unit exactly
    # as it was ("ready", eligible again later) instead of stranding it
    # "in_progress" with no lease and no way for any priority to pick it
    # back up.
    for work_unit_id in work_unit_ids:
        if work_unit_id in leases_by_work_unit:
            continue
        wu_document = work_unit_documents.get(work_unit_id)
        if wu_document is None or wu_document.get("status") not in {
            "ready",
            "in_progress",
            "remediation_required",
        }:
            continue
        if not _dependencies_satisfied(wu_document, work_unit_documents):
            continue
        new_lease_id = f"LEASE-{work_unit_id}-{uuid.uuid4().hex[:8]}"
        lease_receipt, lease_exit = gateway.execute_command(
            _envelope(
                "AcquireWorkerLease",
                target={"kind": "worker_lease", "id": new_lease_id},
                payload={
                    "id": new_lease_id,
                    "run_id": run_id,
                    "work_unit_id": work_unit_id,
                    "worker_id": worker_id,
                },
            )
        )
        if lease_exit != 0:
            return TickResult(
                action="lease_acquisition_failed",
                work_unit_id=work_unit_id,
                details={"errors": lease_receipt.get("errors")},
            )
        if wu_document.get("status") == "ready":
            transition_receipt, transition_exit = gateway.execute_command(
                _envelope(
                    "TransitionWorkUnit",
                    target={
                        "kind": "work_unit",
                        "id": work_unit_id,
                        "expected_revision": wu_document["revision"],
                    },
                    payload={
                        "run_id": run_id,
                        "to_status": "in_progress",
                        "reason": "orchestrator started work",
                    },
                )
            )
            if transition_exit != 0:
                # Do not strand a READY Work Unit behind a lease acquired by a
                # losing concurrent tick.  The next scheduler pass must be
                # able to select it again.
                _release_lease(
                    gateway,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    lease_ref={"lease_id": new_lease_id, "epoch": 1},
                    reason="work unit start transition failed",
                )
                return TickResult(
                    action="transition_failed",
                    work_unit_id=work_unit_id,
                    details={
                        "errors": transition_receipt.get("errors"),
                        "lease_id": new_lease_id,
                    },
                )
        return TickResult(
            action=(
                "started_work_unit"
                if wu_document.get("status") == "ready"
                else "reacquired_work_unit"
            ),
            work_unit_id=work_unit_id,
            details={"lease_id": new_lease_id},
        )

    # Priority 3: dispatch one execution attempt for a Work Unit whose status
    # maps to a dispatchable step and that this caller's own lease already
    # holds fresh and active. Document 6 §11 — with multiple workers ticking
    # concurrently, a worker only ever continues Work Units it currently
    # holds the lease for; it never picks up one another worker owns.
    for work_unit_id, lease_ref in leases_by_work_unit.items():
        lease_document = _read_yaml(
            workspace.ai_team / "runs" / "leases" / f"{lease_ref['lease_id']}.yaml"
        )
        if lease_document is None or lease_document.get("status") != "active":
            continue
        if lease_document.get("worker_id") != worker_id:
            continue
        if not _lease_is_fresh(lease_document, now=now):
            continue
        wu_document = work_unit_documents.get(work_unit_id)
        if wu_document is None:
            continue
        current_status = wu_document.get("status")
        step = _dispatch_step(workspace, run_id, work_unit_id, current_status)
        if step is None:
            continue

        role_id, procedure_id, required_checks = DISPATCH_CONTRACTS[step]
        if step in {"sandbox_implementation", "remediation"}:
            role_id = _resolve_implementation_role(workspace, wu_document)
            if role_id == "frontend-developer":
                from governed_ai.core.design_authority.procedure_select import (
                    ProcedureSelectionError,
                    select_frontend_procedure,
                )

                binding = wu_document.get("design_binding") or {}
                design_mode = binding.get("design_mode")
                try:
                    procedure_id = select_frontend_procedure(
                        design_mode=str(design_mode) if design_mode else None,
                        requested_procedure=None,
                    )
                except ProcedureSelectionError:
                    procedure_id = "implement-approved-design"

        # A previous terminal attempt may already have consumed the final
        # convergence slot.  Demote before trying to create another `started`
        # attempt; otherwise the Core rejects it and a live scheduler can spin
        # forever on `execution_not_authorized` while holding the lease.
        pre_dispatch_exhaustion = _pre_dispatch_exhaustion_reason(
            workspace,
            run_document,
            work_unit_id=work_unit_id,
            step=step,
        )
        if pre_dispatch_exhaustion is not None:
            next_status = NEXT_STATUS_ON_EXHAUSTION.get(str(current_status))
            if next_status is None:
                return TickResult(
                    action="convergence_exhausted",
                    work_unit_id=work_unit_id,
                    details={"step": step, "reason": pre_dispatch_exhaustion},
                )
            transition_receipt, transition_exit = gateway.execute_command(
                _envelope(
                    "TransitionWorkUnit",
                    target={
                        "kind": "work_unit",
                        "id": work_unit_id,
                        "expected_revision": wu_document["revision"],
                    },
                    payload={
                        "run_id": run_id,
                        "to_status": next_status,
                        "reason": (
                            "orchestrator: convergence already exhausted before dispatch "
                            f"({pre_dispatch_exhaustion})"
                        ),
                    },
                )
            )
            if transition_exit != 0:
                return TickResult(
                    action="transition_failed",
                    work_unit_id=work_unit_id,
                    details={"errors": transition_receipt.get("errors")},
                )
            release_receipt, release_exit = _release_lease(
                gateway,
                run_id=run_id,
                work_unit_id=work_unit_id,
                lease_ref=lease_ref,
                reason=f"convergence already exhausted: {pre_dispatch_exhaustion}",
            )
            return TickResult(
                action="demoted_work_unit" if release_exit == 0 else "lease_release_failed",
                work_unit_id=work_unit_id,
                details={
                    "from": current_status,
                    "to": next_status,
                    "reason": pre_dispatch_exhaustion,
                    "errors": release_receipt.get("errors"),
                },
            )
        execution_id = f"EXE-{uuid.uuid4().hex[:8]}"
        attempt_id = f"ATTEMPT-{work_unit_id}-{uuid.uuid4().hex[:8]}"
        attempt_actor_role = (
            "integration-steward" if step == "integration_review" else "control-plane"
        )
        start_receipt, start_exit = gateway.execute_command(
            _envelope(
                "RecordExecutionAttempt",
                target={"kind": "execution_attempt", "id": attempt_id},
                payload={
                    "run_id": run_id,
                    "execution_id": execution_id,
                    "work_unit_id": work_unit_id,
                    "worker_lease_id": lease_ref["lease_id"],
                    "epoch": lease_ref["epoch"],
                    "step": step,
                    "status": "started",
                    "contract": {"role_id": role_id, "procedure_id": procedure_id},
                },
                actor_role_id=attempt_actor_role,
            )
        )
        if start_exit != 0:
            return TickResult(
                action="execution_not_authorized",
                work_unit_id=work_unit_id,
                details={"errors": start_receipt.get("errors")},
            )

        execution_root = workspace.root
        try:
            descriptor = adapter.describe()
        except (AttributeError, NotImplementedError):
            descriptor = None
        isolated_worktree = bool(
            descriptor and descriptor.get("capabilities", {}).get("isolated_worktree")
        )
        if (
            is_unattended_preset(run_document.get("autonomy_preset"))
            and not isolated_worktree
        ):
            failed_receipt, failed_exit = gateway.execute_command(
                _envelope(
                    "RecordExecutionAttempt",
                    target={
                        "kind": "execution_attempt",
                        "id": attempt_id,
                        "expected_revision": 1,
                    },
                    payload={
                        "run_id": run_id,
                        "execution_id": execution_id,
                        "work_unit_id": work_unit_id,
                        "worker_lease_id": lease_ref["lease_id"],
                        "epoch": lease_ref["epoch"],
                        "step": step,
                        "status": "failed",
                        "summary": "adapter cannot guarantee an isolated worker workspace",
                    },
                    actor_role_id=(
                        "integration-steward" if step == "integration_review" else "control-plane"
                    ),
                )
            )
            if failed_exit != 0:
                return TickResult(
                    action="attempt_recording_failed",
                    work_unit_id=work_unit_id,
                    details={"errors": failed_receipt.get("errors")},
                )
            stop_receipt, stop_exit = gateway.execute_command(
                _envelope(
                    "CloseRun",
                    target={
                        "kind": "run",
                        "id": run_id,
                        "expected_revision": run_document["revision"],
                    },
                    payload={
                        "status": "stopped",
                        "reason": "adapter cannot guarantee worker isolation",
                        "stop_condition": "worker_isolation_unguaranteed",
                    },
                )
            )
            return _terminal_run_result(
                gateway,
                close_exit=stop_exit,
                action_ok="run_stopped",
                action_fail="run_stop_failed",
                work_unit_id=work_unit_id,
                details={
                    "stop_condition": "worker_isolation_unguaranteed",
                    "errors": stop_receipt.get("errors"),
                },
            )
        if isolated_worktree:
            try:
                recovery_start_shas = (
                    run_document.get("recovery_start_shas_by_work_unit") or {}
                )
                execution_root = ensure_work_unit_worktree(
                    workspace.root,
                    run_id,
                    work_unit_id,
                    start_sha=(
                        recovery_start_shas.get(work_unit_id)
                        or _checkpoint_start_sha(workspace, work_unit_id)
                    ),
                )
            except GitWorkspaceError as exc:
                failed_receipt, failed_exit = gateway.execute_command(
                    _envelope(
                        "RecordExecutionAttempt",
                        target={
                            "kind": "execution_attempt",
                            "id": attempt_id,
                            "expected_revision": 1,
                        },
                        payload={
                            "run_id": run_id,
                            "execution_id": execution_id,
                            "work_unit_id": work_unit_id,
                            "worker_lease_id": lease_ref["lease_id"],
                            "epoch": lease_ref["epoch"],
                            "step": step,
                            "status": "failed",
                            "summary": f"worker isolation failed: {exc}",
                        },
                    )
                )
                if failed_exit != 0:
                    return TickResult(
                        action="attempt_recording_failed",
                        work_unit_id=work_unit_id,
                        details={"errors": failed_receipt.get("errors")},
                    )
                stop_receipt, stop_exit = gateway.execute_command(
                    _envelope(
                        "CloseRun",
                        target={
                            "kind": "run",
                            "id": run_id,
                            "expected_revision": run_document["revision"],
                        },
                        payload={
                            "status": "stopped",
                            "reason": f"worker isolation failed: {exc}",
                            "stop_condition": "worker_isolation_unguaranteed",
                        },
                    )
                )
                return _terminal_run_result(
                    gateway,
                    close_exit=stop_exit,
                    action_ok="run_stopped",
                    action_fail="run_stop_failed",
                    work_unit_id=work_unit_id,
                    details={
                        "stop_condition": "worker_isolation_unguaranteed",
                        "error": str(exc),
                        "errors": stop_receipt.get("errors"),
                    },
                )
        base_sha = head_sha(execution_root) if execution_root != workspace.root else _git_head(workspace)
        allowed_shell_commands, allowed_paths, accessible_secrets = _execution_envelope_constraints(
            workspace, run_document
        )
        spi_request: ExecutionRequest = {
            "protocol_version": "1.0",
            "execution_id": execution_id,
            "correlation_id": run_id,
            "adapter": _adapter_identity(adapter),
            "contract": _resolve_execution_contract(
                workspace, role_id=role_id, procedure_id=procedure_id
            ),
            "work_unit_id": work_unit_id,
            "requested_at": now.isoformat(),
            "resolved_scope": (wu_document.get("scope") or {}).get("include", []),
            "execution_workspace": str(execution_root),
            "work_unit_snapshot": wu_document,
            "required_checks": list(required_checks),
            "kill_switch_path": str(
                workspace.ai_team
                / "run-authorization-grants"
                / f"{run_document['run_authorization_grant_id']}.json"
            ),
            "run_state_path": str(workspace.ai_team / "runs" / f"{run_id}.yaml"),
            "allowed_shell_commands": allowed_shell_commands,
            "allowed_paths": allowed_paths,
            "accessible_secrets": accessible_secrets,
            "timeout_seconds": resolve_step_timeout_seconds(
                run_document.get("effective_autonomy_policy"),
                step,
                grant_remaining_seconds=_grant_remaining_seconds(
                    workspace, run_document, now=now
                ),
            ),
        }
        if base_sha is not None:
            spi_request["base_sha"] = base_sha
        # Keep ``request`` alias for downstream RecordExecutionAttempt payloads.
        request = spi_request
        context_ref, context_error = _resolve_context_package_ref(
            workspace, wu_document, procedure_id=procedure_id, role_id=role_id
        )
        gateway_accepted = False
        boundary_stop_condition: str | None = None
        boundary_error: str | None = None
        if context_error:
            result = {
                "status": "blocked",
                "summary": context_error,
                "checks": [],
                "artifacts": [],
                "requested_commands": [],
                "usage": {},
                "limitations": ["context_package_incomplete"],
            }
        elif base_sha is None:
            result = {
                "status": "blocked",
                "summary": "execution workspace has no base commit for governed gateway",
                "checks": [],
                "artifacts": [],
                "requested_commands": [],
                "usage": {},
                "limitations": ["missing_base_sha"],
            }
        else:
            if context_ref:
                spi_request["context_package_ref"] = context_ref
            gateway_work_unit = dict(wu_document)
            if context_ref:
                gateway_work_unit["context_package_ref"] = context_ref
            gateway_required_checks = list(required_checks)
            if step in {"sandbox_implementation", "remediation"}:
                explicit_ac_ids = _explicit_acceptance_criterion_ids(wu_document)
                if explicit_ac_ids:
                    gateway_required_checks = list(explicit_ac_ids)
            from governed_ai.core.supervisor.execution_bridge import run_governed_execution

            profile_document = _read_yaml(workspace.ai_team / "project-profile.yaml") or {}
            ceilings_by_work_unit = run_document.get("execution_ceilings_by_work_unit") or {}
            ceiling_document = (
                ceilings_by_work_unit.get(work_unit_id)
                if isinstance(ceilings_by_work_unit, dict)
                else None
            )
            if not isinstance(ceiling_document, dict):
                ceiling_document = run_document.get("execution_ceiling")
            ceiling = (
                sanitize_allowed_paths(list(ceiling_document.get("allowed_paths") or []))
                if isinstance(ceiling_document, dict) and "allowed_paths" in ceiling_document
                else None
            )
            try:
                outcome = run_governed_execution(
                    workspace,
                    adapter=adapter,
                    work_unit=gateway_work_unit,
                    run_id=run_id,
                    execution_id=execution_id,
                    lease_id=str(lease_ref["lease_id"]),
                    epoch=int(lease_ref["epoch"]),
                    role_id=role_id,
                    procedure_id=procedure_id,
                    base_sha=base_sha,
                    grant_allowed_paths=list(allowed_paths or []),
                    grant_axis_present=allowed_paths is not None,
                    allowed_shell_commands=allowed_shell_commands,
                    required_checks=gateway_required_checks,
                    accessible_secrets=accessible_secrets,
                    profile=profile_document if isinstance(profile_document, dict) else None,
                    spi_request=dict(spi_request),
                    execution_workspace=execution_root,
                    use_ephemeral_workspace=False,
                    run_independent_verification=True,
                    instance_id=f"tick-{worker_id}",
                    worker_id=worker_id,
                    execution_ceiling_paths=ceiling,
                    fence_authoritative_lease=True,
                )
            except Exception as exc:  # noqa: BLE001 - adapter/gateway boundary must fail closed
                result = {
                    "status": "blocked",
                    "summary": f"execution gateway failed: {type(exc).__name__}: {exc}",
                    "checks": [],
                    "artifacts": [],
                    "requested_commands": [],
                    "usage": {},
                    "limitations": ["execution_gateway_error"],
                }
            else:
                if outcome.ok and outcome.result is not None:
                    result = dict(outcome.result)
                    gateway_accepted = True
                else:
                    error = outcome.error
                    code = error.code if error else "execution_gateway_rejected"
                    if code == "agent_status_not_succeeded" and outcome.result is not None:
                        # Preserve the strictly canonical non-success result for
                        # failure accounting and decision proposals. It remains
                        # rejected and can never authorize promotion/checkpoint
                        # verification or workflow advancement.
                        result = dict(outcome.result)
                        result["limitations"] = [
                            *list(result.get("limitations") or []),
                            code,
                        ]
                        continue_after_gateway_rejection = True
                    else:
                        continue_after_gateway_rejection = False
                    # Gateway rejection is a failed attempt, not a human-blocked pause,
                    # unless the error is an explicit pre-launch context/capability block.
                    if not continue_after_gateway_rejection:
                        mapped = "blocked" if code in {
                            "unsupported_role",
                            "unsupported_procedure",
                            "missing_adapter_capability",
                            "empty_effective_scope",
                            "contradictory_path_policy",
                        } else "failed"
                        result = {
                            "status": mapped,
                            "summary": (
                                f"execution gateway rejected: "
                                f"{code}: "
                                f"{error.message if error else 'no details'}"
                            ),
                            "checks": [],
                            "artifacts": [],
                            "requested_commands": [],
                            "usage": {},
                            "limitations": [code],
                            "workspace": {"base_sha": base_sha},
                        }
                    if code in {"scope_violation", "forbidden_control_plane_path"}:
                        boundary_stop_condition = "out_of_workspace_write"
                        boundary_error = error.message if error else code
        if isolated_worktree and base_sha is not None:
            # Persist the scheduler-observed base, never an agent-supplied value.
            # Recovery after a boundary violation can then fence off the bad
            # commit while retaining all prior validated/WIP product work.
            result = dict(result)
            workspace_meta = dict(result.get("workspace") or {})
            workspace_meta["base_sha"] = base_sha
            result["workspace"] = workspace_meta
        status = result.get("status", "failed")
        if status == "timed_out" and isolated_worktree and execution_root != workspace.root:
            try:
                dirty = list_uncommitted_files(execution_root)
                boundary = None
                if dirty:
                    boundary = boundary_error_for_changed_files(
                        dirty,
                        work_unit_id=work_unit_id,
                        wu_document=wu_document,
                        allowed_paths=allowed_paths,
                    )
                wip_sha = None
                if dirty and boundary is None:
                    wip_sha = create_unverified_wip_commit(
                        execution_root,
                        work_unit_id=work_unit_id,
                        paths=dirty,
                    )
                elif dirty and boundary is not None:
                    result = dict(result)
                    result["summary"] = (
                        f"{result.get('summary') or ''} "
                        f"WIP checkpoint skipped: {boundary}"
                    ).strip()
                head = head_sha(execution_root)
                salvage_sha = wip_sha or (head if base_sha and head != base_sha else None)
                if salvage_sha and base_sha and boundary is None:
                    files = changed_files(execution_root, base_sha, salvage_sha)
                    boundary = boundary_error_for_changed_files(
                        files,
                        work_unit_id=work_unit_id,
                        wu_document=wu_document,
                        allowed_paths=allowed_paths,
                    )
                    if boundary is None:
                        result = dict(result)
                        workspace_meta = dict(result.get("workspace") or {})
                        workspace_meta["base_sha"] = base_sha
                        workspace_meta["result_sha"] = salvage_sha
                        result["workspace"] = workspace_meta
                        result["summary"] = (
                            f"{result.get('summary') or ''} "
                            f"Unverified WIP checkpoint saved at {salvage_sha}."
                        ).strip()
            except GitWorkspaceError:
                pass
        if status == "succeeded":
            # When the Agent Execution Gateway already accepted the result, do not
            # re-consume or re-interpret the raw adapter payload — only the
            # canonical GatewayOutcome may authorize success / promotion.
            if not gateway_accepted:
                evidence_error = _evidence_error(
                    result,
                    required_checks=required_checks,
                    require_changed_sha=step in {"sandbox_implementation", "remediation"},
                    base_sha=base_sha,
                    work_unit=wu_document,
                )
                if evidence_error:
                    status = "failed"
                    result = dict(result)
                    result["summary"] = f"{result.get('summary') or ''} Evidence gate: {evidence_error}".strip()
        if (
            status == "succeeded"
            and step in {"sandbox_implementation", "remediation"}
            and isolated_worktree
            and not gateway_accepted
        ):
            boundary_violation = _implementation_boundary_error(
                execution_root=execution_root,
                base_sha=base_sha,
                result=result,
                wu_document=wu_document,
                run_document=run_document,
                allowed_paths=allowed_paths or [],
            )
            if boundary_violation:
                boundary_error, boundary_stop_condition = boundary_violation
                status = "failed"
                result = dict(result)
                result["summary"] = (
                    f"{result.get('summary') or ''} Execution boundary: {boundary_error}"
                ).strip()

        integration_merge: tuple[str, str] | None = None
        if status == "succeeded" and step == "integration_review":
            # The agent may have run long enough for its lease to be replaced.
            # Fence once more immediately before mutating the shared
            # integration branch; a superseded worker may leave artifacts in
            # its isolated worktree but can never merge them.
            fence_receipt, fence_exit = gateway.execute_command(
                _envelope(
                    "RecordWorkerHeartbeat",
                    target={"kind": "worker_lease", "id": lease_ref["lease_id"]},
                    payload={"run_id": run_id, "epoch": lease_ref["epoch"]},
                )
            )
            if fence_exit != 0:
                return TickResult(
                    action="fenced_before_integration",
                    work_unit_id=work_unit_id,
                    details={"errors": fence_receipt.get("errors")},
                )
            try:
                integration_merge = merge_and_revalidate(
                    workspace.root,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    integration_branch=run_document["integration_branch"],
                    verification_command=_integration_verification_command(workspace),
                )
            except GitWorkspaceError as exc:
                status = "failed"
                result = dict(result)
                result["summary"] = (
                    f"{result.get('summary') or ''} Integration gate: {exc}"
                ).strip()
            else:
                merge_sha, revalidation_digest = integration_merge
                result = dict(result)
                result["summary"] = (
                    f"{result.get('summary') or ''} Integrated as {merge_sha}."
                ).strip()
                result["artifacts"] = [
                    *result.get("artifacts", []),
                    {
                        "kind": "integration_revalidation",
                        "path": f"git:{run_document['integration_branch']}@{merge_sha}",
                        "sha256": revalidation_digest,
                    },
                ]

        attempt_taxonomy = classify_attempt_failure(
            status=status,
            step=step,
            summary=str(result.get("summary") or ""),
            limitations=list(result.get("limitations") or []),
        ) or {}
        attempt_receipt, attempt_exit = gateway.execute_command(
            _envelope(
                "RecordExecutionAttempt",
                target={
                    "kind": "execution_attempt",
                    "id": attempt_id,
                    "expected_revision": 1,
                },
                payload={
                    "run_id": run_id,
                    "execution_id": execution_id,
                    "work_unit_id": work_unit_id,
                    "worker_lease_id": lease_ref["lease_id"],
                    "epoch": lease_ref["epoch"],
                    "step": step,
                    "status": status,
                    "summary": result.get("summary"),
                    "checks": result.get("checks", []),
                    "artifacts": result.get("artifacts", []),
                    "workspace": result.get("workspace", {}),
                    "contract": result.get("contract", request["contract"]),
                    "requested_commands": result.get("requested_commands", []),
                    "usage": result.get("usage", {}),
                    "duration_ms": result.get("duration_ms"),
                    "provider": result.get("provider", {}),
                    **attempt_taxonomy,
                },
                actor_role_id=attempt_actor_role,
            )
        )
        if attempt_exit != 0:
            stop_condition = _global_stop_condition(workspace, run_document, now=datetime.now(UTC))
            if stop_condition:
                stop_receipt, stop_exit = gateway.execute_command(
                    _envelope(
                        "CloseRun",
                        target={
                            "kind": "run",
                            "id": run_id,
                            "expected_revision": run_document["revision"],
                        },
                        payload={
                            "status": "stopped",
                            "reason": f"run-reliability-controller: {stop_condition}",
                            "stop_condition": stop_condition,
                        },
                    )
                )
                return _terminal_run_result(
                    gateway,
                    close_exit=stop_exit,
                    action_ok="run_stopped",
                    action_fail="run_stop_failed",
                    work_unit_id=work_unit_id,
                    details={
                        "stop_condition": stop_condition,
                        "errors": stop_receipt.get("errors"),
                    },
                )
            return TickResult(
                action="attempt_recording_failed",
                work_unit_id=work_unit_id,
                details={"errors": attempt_receipt.get("errors")},
            )

        if status in {"failed", "timed_out", "blocked", "cancelled"}:
            # Best-effort: a friction signal derived from the attempt itself,
            # so silent failures still surface in retrospectives even when no
            # human or agent remembers to record an observation by hand. Never
            # blocks the tick — an installed client project may disable
            # feedback recording, and that must not affect scheduling.
            auto_fields = classify_auto_observation(step=step, status=status)
            raw_symptom = (
                result.get("summary")
                or f"execution attempt for step {step!r} ended with status {status!r}"
            )
            symptom = str(raw_symptom)
            if len(symptom) > _MAX_AUTO_SYMPTOM:
                symptom = symptom[: _MAX_AUTO_SYMPTOM - 1] + "…"
            auto_payload = {
                "category": auto_fields["category"],
                "symptom": symptom,
                "severity": (
                    "high"
                    if is_unattended_preset(run_document.get("autonomy_preset"))
                    else "medium"
                ),
                "classification": auto_fields["classification"],
                "work_unit": work_unit_id,
                "phase": step,
                "recorded_by": "orchestrator:auto",
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": status in {"failed", "timed_out"},
                    "human_intervention": status == "blocked",
                    "affected_work_units": [work_unit_id],
                },
                "evidence_refs": [attempt_id, execution_id],
                "recurrence_key": f"auto:{step}:{status}",
            }
            if auto_fields.get("candidate_improvement"):
                auto_payload["candidate_improvement"] = auto_fields[
                    "candidate_improvement"
                ]
            gateway.execute_command(
                _envelope(
                    "RecordObservation",
                    target={"kind": "observation", "id": "new"},
                    payload=auto_payload,
                )
            )

        if boundary_stop_condition:
            # Document 6 §9.5 — a write outside the authorized workspace stops
            # the whole Run, not just this Work Unit. The failed attempt above
            # is already durably recorded; this closes the Run around it.
            stop_receipt, stop_exit = gateway.execute_command(
                _envelope(
                    "CloseRun",
                    target={
                        "kind": "run",
                        "id": run_id,
                        "expected_revision": run_document["revision"],
                    },
                    payload={
                        "status": "stopped",
                        "reason": (
                            f"run-reliability-controller: "
                            f"{boundary_error or boundary_stop_condition}"
                        ),
                        "stop_condition": boundary_stop_condition,
                    },
                )
            )
            return _terminal_run_result(
                gateway,
                close_exit=stop_exit,
                action_ok="run_stopped",
                action_fail="run_stop_failed",
                work_unit_id=work_unit_id,
                details={
                    "stop_condition": boundary_stop_condition,
                    "errors": stop_receipt.get("errors"),
                },
            )

        if integration_merge is not None:
            merge_sha, revalidation_digest = integration_merge
            merge_id = f"MERGE-{work_unit_id}-{uuid.uuid4().hex[:8]}"
            merge_receipt, merge_exit = gateway.execute_command(
                _envelope(
                    "RecordIntegrationMerge",
                    target={"kind": "integration_merge", "id": merge_id},
                    payload={
                        "run_id": run_id,
                        "work_unit_id": work_unit_id,
                        "worker_lease_id": lease_ref["lease_id"],
                        "epoch": lease_ref["epoch"],
                        "conflict_resolution_attempts": _integration_conflict_attempts(
                            workspace, run_id, work_unit_id
                        ),
                        "revalidation_passed": True,
                        "revalidation_evidence": [revalidation_digest, merge_sha],
                    },
                    actor_role_id="integration-steward",
                )
            )
            if merge_exit != 0:
                return TickResult(
                    action="integration_recording_failed",
                    work_unit_id=work_unit_id,
                    details={"errors": merge_receipt.get("errors"), "merge_sha": merge_sha},
                )

        attempt_details = attempt_receipt.get("details") or {}
        if attempt_details.get("global_stop_condition"):
            stop_condition = str(attempt_details["global_stop_condition"])
            stop_receipt, stop_exit = gateway.execute_command(
                _envelope(
                    "CloseRun",
                    target={
                        "kind": "run",
                        "id": run_id,
                        "expected_revision": run_document["revision"],
                    },
                    payload={
                        "status": "stopped",
                        "reason": "run-reliability-controller: execution budget exhausted",
                        "stop_condition": stop_condition,
                    },
                )
            )
            return _terminal_run_result(
                gateway,
                close_exit=stop_exit,
                action_ok="run_stopped",
                action_fail="run_stop_failed",
                work_unit_id=work_unit_id,
                details={"stop_condition": stop_condition, "errors": stop_receipt.get("errors")},
            )
        systemic_stop = _global_stop_condition(workspace, run_document, now=datetime.now(UTC))
        if systemic_stop == "repeated_systemic_failure":
            stop_receipt, stop_exit = gateway.execute_command(
                _envelope(
                    "CloseRun",
                    target={
                        "kind": "run",
                        "id": run_id,
                        "expected_revision": run_document["revision"],
                    },
                    payload={
                        "status": "stopped",
                        "reason": "identical failures affected multiple Work Units",
                        "stop_condition": systemic_stop,
                    },
                )
            )
            return _terminal_run_result(
                gateway,
                close_exit=stop_exit,
                action_ok="run_stopped",
                action_fail="run_stop_failed",
                work_unit_id=work_unit_id,
                details={"stop_condition": systemic_stop, "errors": stop_receipt.get("errors")},
            )

        heartbeat_receipt, heartbeat_exit = gateway.execute_command(
            _envelope(
                "RecordWorkerHeartbeat",
                target={"kind": "worker_lease", "id": lease_ref["lease_id"]},
                payload={"run_id": run_id, "epoch": lease_ref["epoch"]},
            )
        )
        if heartbeat_exit != 0:
            return TickResult(
                action="heartbeat_failed",
                work_unit_id=work_unit_id,
                details={"errors": heartbeat_receipt.get("errors")},
            )

        checkpoint_receipt, checkpoint_exit = gateway.execute_command(
            _envelope(
                "WriteCheckpoint",
                target={"kind": "checkpoint", "id": work_unit_id},
                payload={
                    "run_id": run_id,
                    "worker_lease_id": lease_ref["lease_id"],
                    "epoch": lease_ref["epoch"],
                    "last_commit": (
                        (result.get("workspace") or {}).get("promoted_sha")
                        if gateway_accepted
                        else (result.get("workspace") or {}).get("result_sha")
                    ),
                    "last_validated_workflow_state": current_status,
                    "executed_commands": [str(item) for item in result.get("requested_commands", [])],
                    "artifacts": [str(item.get("path")) for item in result.get("artifacts", [])],
                    "next_step": step,
                    "verification_status": (
                        "unverified"
                        if status == "timed_out"
                        and (result.get("workspace") or {}).get("result_sha")
                        else "verified"
                        if status == "succeeded" and gateway_accepted
                        else None
                    ),
                },
            )
        )
        if checkpoint_exit != 0:
            return TickResult(
                action="checkpoint_failed",
                work_unit_id=work_unit_id,
                details={"errors": checkpoint_receipt.get("errors")},
            )

        # Document 6 §7.3 — escalation is automatic and immediate; process
        # before any advancement so a discovered higher risk can pause the WU
        # even when the attempt itself succeeded.
        risk_escalation = result.get("risk_escalation")
        if isinstance(risk_escalation, dict) and risk_escalation.get("new_risk_class"):
            run_document = yaml.safe_load(
                (workspace.ai_team / "runs" / f"{run_id}.yaml").read_text(encoding="utf-8")
            )
            escalate_receipt, escalate_exit = gateway.execute_command(
                _envelope(
                    "EscalateWorkUnitRisk",
                    target={
                        "kind": "run",
                        "id": run_id,
                        "expected_revision": run_document["revision"],
                    },
                    payload={
                        "work_unit_id": work_unit_id,
                        "new_risk_class": risk_escalation["new_risk_class"],
                        "reason": risk_escalation.get("reason")
                        or "adapter reported higher risk during execution",
                    },
                )
            )
            if escalate_exit != 0:
                return TickResult(
                    action="risk_escalation_failed",
                    work_unit_id=work_unit_id,
                    details={"errors": escalate_receipt.get("errors")},
                )
            wu_document = yaml.safe_load(
                (workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").read_text(
                    encoding="utf-8"
                )
            )
            if (escalate_receipt.get("details") or {}).get("paused"):
                # EscalateWorkUnitRisk already released any active lease when
                # pausing (§7.3) — do not issue a second ReleaseWorkerLease.
                return TickResult(
                    action="paused_for_risk_escalation",
                    work_unit_id=work_unit_id,
                    details={
                        "attempt_id": attempt_id,
                        "new_risk_class": risk_escalation["new_risk_class"],
                        "paused": True,
                    },
                )

        # Document 6 §5.3/§12.2 — mandate-matcher proposes; Core validates.
        # Handled for any attempt status: an unresolved fork pauses the WU
        # even if the underlying step otherwise succeeded.
        decision_proposal = result.get("decision_proposal")
        if (
            isinstance(decision_proposal, dict)
            and decision_proposal.get("trigger")
            and decision_proposal.get("proposed_entry_id")
        ):
            decision_id = f"DECISION-{uuid.uuid4().hex[:12].upper()}"
            decision_receipt, decision_exit = gateway.execute_command(
                _envelope(
                    "ResolveRunDecision",
                    target={"kind": "run_decision", "id": decision_id},
                    payload={
                        "run_id": run_id,
                        "work_unit_id": work_unit_id,
                        "trigger": decision_proposal.get("trigger"),
                        "proposed_entry_id": decision_proposal.get("proposed_entry_id"),
                        "evidence": decision_proposal.get("evidence") or [],
                        "environment": decision_proposal.get("environment"),
                    },
                    actor_role_id="mandate-matcher",
                )
            )
            if decision_exit != 0:
                return TickResult(
                    action="decision_resolution_failed",
                    work_unit_id=work_unit_id,
                    details={"errors": decision_receipt.get("errors")},
                )
            resolved = bool((decision_receipt.get("details") or {}).get("resolved"))
            if not resolved:
                _release_lease(
                    gateway,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    lease_ref=lease_ref,
                    reason="decision requires human authority",
                )
                return TickResult(
                    action="paused_awaiting_human",
                    work_unit_id=work_unit_id,
                    details={
                        "decision_id": decision_id,
                        "resolved": False,
                        "rejection_reason": (decision_receipt.get("details") or {}).get(
                            "rejection_reason"
                        ),
                    },
                )
            if status != "succeeded":
                return TickResult(
                    action="decision_resolved",
                    work_unit_id=work_unit_id,
                    details={
                        "decision_id": decision_id,
                        "resolved": True,
                        "rejection_reason": None,
                    },
                )

        # Document 6 §9.3/orchestrator.json — a success always advances the
        # Work Unit, even if this same attempt also happened to hit the
        # numeric attempt cap: there is no reason to demote a step that just
        # succeeded. Only a non-success that trips convergence exhaustion
        # demotes it; anything else just retries on a later tick.
        if status == "succeeded":
            if step == "security_review":
                return TickResult(
                    action="completed_security_review",
                    work_unit_id=work_unit_id,
                    details={"attempt_id": attempt_id},
                )
            next_status = NEXT_STATUS_ON_SUCCESS.get(current_status)
            if next_status is not None:
                transition_receipt, transition_exit = gateway.execute_command(
                    _envelope(
                        "TransitionWorkUnit",
                        target={
                            "kind": "work_unit",
                            "id": work_unit_id,
                            "expected_revision": wu_document["revision"],
                        },
                        payload={
                            "run_id": run_id,
                            "to_status": next_status,
                            "reason": f"orchestrator: {step} succeeded",
                        },
                    )
                )
                if transition_exit != 0:
                    return TickResult(
                        action="transition_failed",
                        work_unit_id=work_unit_id,
                        details={"errors": transition_receipt.get("errors")},
                    )
                if next_status == "human_test":
                    release_receipt, release_exit = _release_lease(
                        gateway,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                        lease_ref=lease_ref,
                        reason="ready for human morning review",
                    )
                    if release_exit != 0:
                        return TickResult(
                            action="lease_release_failed",
                            work_unit_id=work_unit_id,
                            details={"errors": release_receipt.get("errors")},
                        )
                    retrospective_receipt, retrospective_exit = gateway.execute_command(
                        _envelope(
                            "GenerateRetrospective",
                            target={"kind": "retrospective", "id": "new"},
                            payload={"scope": "work_unit", "work_unit_id": work_unit_id},
                        )
                    )
                    retrospective_details = (
                        {"retrospective_id": retrospective_receipt["affected"][0]["id"]}
                        if retrospective_exit == 0
                        else {"retrospective_errors": retrospective_receipt.get("errors")}
                    )
                else:
                    retrospective_details = {}
                return TickResult(
                    action="advanced_work_unit",
                    work_unit_id=work_unit_id,
                    details={
                        "attempt_id": attempt_id,
                        "from": current_status,
                        "to": next_status,
                        **retrospective_details,
                    },
                )
        else:
            if status == "blocked":
                blocked_status = (
                    "blocked"
                    if current_status in {"in_progress", "remediation_required"}
                    else "remediation_required"
                )
                transition_receipt, transition_exit = gateway.execute_command(
                    _envelope(
                        "TransitionWorkUnit",
                        target={
                            "kind": "work_unit",
                            "id": work_unit_id,
                            "expected_revision": wu_document["revision"],
                        },
                        payload={
                            "run_id": run_id,
                            "to_status": blocked_status,
                            "reason": f"orchestrator paused blocked step: {result.get('summary')}",
                        },
                    )
                )
                if transition_exit != 0:
                    return TickResult(
                        action="transition_failed",
                        work_unit_id=work_unit_id,
                        details={"errors": transition_receipt.get("errors")},
                    )
                release_receipt, release_exit = _release_lease(
                    gateway,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    lease_ref=lease_ref,
                    reason="worker blocked and requires human intervention",
                )
                return TickResult(
                    action="paused_work_unit" if release_exit == 0 else "lease_release_failed",
                    work_unit_id=work_unit_id,
                    details={
                        "attempt_id": attempt_id,
                        "to": blocked_status,
                        "errors": release_receipt.get("errors"),
                    },
                )
            exhaustion_reason = (attempt_receipt.get("details") or {}).get(
                "convergence_exhaustion_reason"
            )
            if exhaustion_reason is not None:
                next_status = NEXT_STATUS_ON_EXHAUSTION.get(current_status)
                if next_status is not None:
                    transition_receipt, transition_exit = gateway.execute_command(
                        _envelope(
                            "TransitionWorkUnit",
                            target={
                                "kind": "work_unit",
                                "id": work_unit_id,
                                "expected_revision": wu_document["revision"],
                            },
                            payload={
                                "run_id": run_id,
                                "to_status": next_status,
                                "reason": f"orchestrator: convergence exhausted ({exhaustion_reason})",
                            },
                        )
                    )
                    if transition_exit != 0:
                        return TickResult(
                            action="transition_failed",
                            work_unit_id=work_unit_id,
                            details={"errors": transition_receipt.get("errors")},
                        )
                    _release_lease(
                        gateway,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                        lease_ref=lease_ref,
                        reason=f"convergence exhausted: {exhaustion_reason}",
                    )
                    return TickResult(
                        action="demoted_work_unit",
                        work_unit_id=work_unit_id,
                        details={
                            "attempt_id": attempt_id,
                            "from": current_status,
                            "to": next_status,
                            "reason": exhaustion_reason,
                        },
                    )

        return TickResult(
            action="recorded_attempt",
            work_unit_id=work_unit_id,
            details={"attempt_id": attempt_id, "status": status},
        )

    # Priority 4: materialize the preset's promised deliverable, then close the
    # technical session. Human acceptance/G3 remains untouched: maximal mode
    # produces a candidate *ready for* G3 and never approves or releases it.
    if (
        is_unattended_preset(run_document.get("autonomy_preset"))
        and _all_work_units_ready_for_morning_review(work_unit_ids, work_unit_documents)
    ):
        if run_document.get("autonomy_preset") == "unattended_maximal":
            candidate_id = f"RC-{run_id}"
            candidate_path = workspace.ai_team / "release-candidates" / f"{candidate_id}.yaml"
            if not candidate_path.is_file():
                try:
                    integration_root = ensure_integration_worktree(
                        workspace.root, run_id, run_document["integration_branch"]
                    )
                    integration_sha = head_sha(integration_root)
                except GitWorkspaceError as exc:
                    return TickResult(
                        action="release_candidate_failed",
                        work_unit_id=None,
                        details={"error": str(exc)},
                    )
                candidate_receipt, candidate_exit = gateway.execute_command(
                    _envelope(
                        "RegisterReleaseCandidate",
                        target={"kind": "release_candidate", "id": candidate_id},
                        payload={
                            "id": candidate_id,
                            "run_id": run_id,
                            "status": "ready_for_g3",
                            "code_revisions": [integration_sha],
                            "included_work_units": list(work_unit_ids),
                            "rollback_plan": (
                                "Revert the integration-branch merge commits; no protected "
                                "branch or production action is authorized by this Run."
                            ),
                            "target_environment": "human_selected_after_g3",
                            "g3": {
                                "status": "pending",
                                "requires_human_authorization": True,
                            },
                        },
                        actor_role_id="release-agent",
                    )
                )
                if candidate_exit != 0:
                    return TickResult(
                        action="release_candidate_failed",
                        work_unit_id=None,
                        details={"errors": candidate_receipt.get("errors")},
                    )
                return TickResult(
                    action="registered_release_candidate",
                    work_unit_id=None,
                    details={"release_candidate_id": candidate_id, "revision": integration_sha},
                )

        close_receipt, close_exit = gateway.execute_command(
            _envelope(
                "CloseRun",
                target={
                    "kind": "run",
                    "id": run_id,
                    "expected_revision": run_document["revision"],
                },
                payload={
                    "status": "completed",
                    "reason": "all Work Units are ready for grouped human morning review",
                },
            )
        )
        retrospective_details = {}
        if close_exit == 0:
            retrospective_receipt, retrospective_exit = gateway.execute_command(
                _envelope(
                    "GenerateRetrospective",
                    target={"kind": "retrospective", "id": "new"},
                    payload={"scope": "project"},
                )
            )
            retrospective_details = (
                {"retrospective_id": retrospective_receipt["affected"][0]["id"]}
                if retrospective_exit == 0
                else {"retrospective_errors": retrospective_receipt.get("errors")}
            )
            # ADR-009: consented projects remount full feedback without extra gates.
            retrospective_details.update(_best_effort_submit_feedback(gateway))
        return TickResult(
            action="run_completed" if close_exit == 0 else "run_completion_failed",
            work_unit_id=None,
            details={"errors": close_receipt.get("errors"), **retrospective_details},
        )

    if (
        not _run_has_dispatchable_work(
            workspace, run_document, work_unit_documents, now=now
        )
        and _run_awaits_human(work_unit_documents)
    ):
        waiting = [
            work_unit_id
            for work_unit_id, document in work_unit_documents.items()
            if document is not None and document.get("status") in _HUMAN_WAIT_STATUSES
        ]
        return TickResult(
            action="awaiting_human",
            work_unit_id=None,
            details={
                "waiting_work_unit_ids": waiting,
                "reason": "remaining work units require human action; tick cannot progress them",
            },
        )

    if (
        not _run_has_dispatchable_work(
            workspace, run_document, work_unit_documents, now=now
        )
        and _should_stop_for_no_dispatchable_work(work_unit_documents)
    ):
        stop_receipt, stop_exit = gateway.execute_command(
            _envelope(
                "CloseRun",
                target={
                    "kind": "run",
                    "id": run_id,
                    "expected_revision": run_document["revision"],
                },
                payload={
                    "status": "stopped",
                    "reason": "no dispatchable work remains and no active worker progress",
                    "stop_condition": "no_dispatchable_work",
                },
            )
        )
        return _terminal_run_result(
            gateway,
            close_exit=stop_exit,
            action_ok="run_stopped",
            action_fail="run_stop_failed",
            work_unit_id=None,
            details={
                "stop_condition": "no_dispatchable_work",
                "errors": stop_receipt.get("errors"),
            },
        )

    return TickResult(action="idle", work_unit_id=None)
