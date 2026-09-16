"""Bridge: Supervisor / orchestrator invoke adapters only via Agent Execution Gateway."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_file
from governed_ai.core.design_authority.security import (
    DesignSecurityError,
    assert_relative_workspace_path,
)
from governed_ai.core.design_authority.visual_capabilities import merge_visual_capabilities
from governed_ai.core.execution_gateway.capabilities import build_capability_descriptor
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.execution_gateway.gateway import (
    AgentExecutionGateway,
    GatewayOutcome,
)
from governed_ai.core.execution_gateway.progress import ProgressEventType, is_useful_progress
from governed_ai.core.execution_gateway.scope import resolve_role_write_paths
from governed_ai.core.supervisor import journal
from governed_ai.core.workspace import Workspace


def _materialize_visual_attachments(
    *,
    context_package: dict[str, Any],
    project_root: Path,
) -> list[dict[str, Any]]:
    """Copy authoritative local design references into a controlled attachment area.

    Fail-closed: missing files or content-hash mismatches refuse execution.
    """
    design = context_package.get("design")
    if not isinstance(design, dict):
        return []
    references = design.get("references")
    if not isinstance(references, list):
        return []

    root = project_root.resolve()
    attachments: list[dict[str, Any]] = []
    for ref in references:
        if not isinstance(ref, dict):
            continue
        attachment_hint = ref.get("adapter_attachment") or {}
        if not isinstance(attachment_hint, dict):
            attachment_hint = {}
        authority = str(ref.get("authority_level") or "")
        must_read = bool(attachment_hint.get("must_be_readable")) or authority == "authoritative"
        source_path = str(ref.get("source_path") or attachment_hint.get("path") or "").strip()
        if not source_path or not must_read:
            continue

        artifact_id = str(ref.get("design_artifact_id") or "unknown")
        expected_hash = str(ref.get("content_hash") or "")
        try:
            absolute = assert_relative_workspace_path(root, source_path)
        except DesignSecurityError as exc:
            raise ExecutionGatewayError(
                StructuredError(
                    code="design_attachment_unavailable",
                    message=f"design reference path refused: {exc.message}",
                    path="context_package.design.references",
                    details={
                        "design_artifact_id": artifact_id,
                        "source_path": source_path,
                        "security_code": exc.code,
                    },
                )
            ) from exc
        if not absolute.is_file():
            raise ExecutionGatewayError(
                StructuredError(
                    code="design_attachment_unavailable",
                    message=f"design reference file missing: {source_path}",
                    path="context_package.design.references",
                    details={
                        "design_artifact_id": artifact_id,
                        "source_path": source_path,
                    },
                )
            )
        actual_hash = sha256_file(absolute)
        if expected_hash and actual_hash != expected_hash:
            raise ExecutionGatewayError(
                StructuredError(
                    code="design_attachment_hash_mismatch",
                    message="design reference content hash mismatch after re-hash",
                    path="context_package.design.references",
                    details={
                        "design_artifact_id": artifact_id,
                        "source_path": source_path,
                        "expected": expected_hash,
                        "actual": actual_hash,
                    },
                )
            )

        dest_dir = root / ".ai-team" / "execution-attachments" / artifact_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / absolute.name
        shutil.copy2(absolute, dest_path)
        attachments.append(
            {
                "design_artifact_id": artifact_id,
                "path": str(dest_path.resolve()),
                "content_hash": actual_hash,
                "authority_level": authority or None,
            }
        )
    return attachments


def align_spi_resolved_scope(merged: dict[str, Any]) -> dict[str, Any]:
    """Set SPI ``resolved_scope`` from the compiled ``contract.effective_scope``.

    Document 12 §2.2: symbolic role paths (``<work-unit-scope>``) are resolved
    by the core before transmission; the Adaptateur must not interpret them.
    The orchestrator fills ``resolved_scope`` with the raw Work Unit include as
    a pre-compile placeholder (it does not yet have the intersection). After
    ``compile_request``, ``contract.effective_scope`` is the authoritative
    intersection (WU ∩ grant ∩ role ∩ adapter ∩ ceiling). This copies that
    list onto the SPI field the Adaptateur and agent prompt actually read.
    """
    effective = (merged.get("contract") or {}).get("effective_scope")
    if isinstance(effective, list):
        merged["resolved_scope"] = [str(item) for item in effective]
    return merged


class SpiCompatibleAdapter:
    """Wrap an SPI adapter so the gateway can invoke it with a merged request.

    The Agent Execution Gateway speaks the canonical contract; product adapters
    still expect ``protocol_version``, ``work_unit_snapshot``, etc.
    This wrapper merges the legacy SPI envelope with the canonical request and
    forces ``execution_workspace`` from the gateway.
    """

    def __init__(self, adapter: Any, *, spi_request: dict[str, Any]) -> None:
        self._adapter = adapter
        self._spi_request = dict(spi_request)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        merged = {**self._spi_request, **request}
        legacy_contract = dict(self._spi_request.get("contract") or {})
        gateway_contract = dict(request.get("contract") or {})
        merged["contract"] = {**legacy_contract, **gateway_contract}
        if request.get("execution_workspace"):
            merged["execution_workspace"] = request["execution_workspace"]
        if "protocol_version" not in merged:
            merged["protocol_version"] = self._spi_request.get("protocol_version") or "1.0"

        context_package = merged.get("context_package")
        if not isinstance(context_package, dict):
            context_package = request.get("context_package")
        if isinstance(context_package, dict):
            merged["context_package"] = context_package
            workspace_raw = merged.get("execution_workspace")
            if workspace_raw:
                project_root = Path(str(workspace_raw))
                merged["visual_attachments"] = _materialize_visual_attachments(
                    context_package=context_package,
                    project_root=project_root,
                )

        align_spi_resolved_scope(merged)
        return self._adapter.execute(merged)


def _bundle_role_procedures(
    workspace: Workspace,
) -> tuple[set[str], dict[str, set[str]], dict[str, list[str]]]:
    """Compile real role/procedure attachments from the published active bundle."""
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    known_roles: set[str] = set()
    role_procedures: dict[str, set[str]] = {}
    role_write_paths: dict[str, list[str]] = {}
    for relative in manifest.get("roles") or []:
        role_path = bundle_dir / str(relative)
        role = json.loads(role_path.read_text(encoding="utf-8"))
        role_id = str(role.get("role_id") or "")
        if not role_id:
            continue
        known_roles.add(role_id)
        role_procedures[role_id] = {
            str(item.get("procedure_id"))
            for item in (role.get("procedure_refs") or [])
            if isinstance(item, dict) and item.get("procedure_id")
        }
        writes = role.get("writes") or {}
        product = writes.get("product") if isinstance(writes, dict) else None
        paths = product.get("paths") if isinstance(product, dict) else None
        role_write_paths[role_id] = [str(item) for item in (paths or [])]
    return known_roles, role_procedures, role_write_paths


def _default_capabilities(
    adapter: Any,
    *,
    role_procedures: dict[str, set[str]],
) -> dict[str, Any]:
    describe = getattr(adapter, "describe", None)
    adapter_id = "external"
    adapter_version = "1.0.0"
    protocol_versions = ["1.0"]
    declared_caps: dict[str, Any] = {}
    if callable(describe):
        try:
            descriptor = describe()
            adapter_id = str(descriptor.get("adapter_id") or adapter_id)
            adapter_version = str(descriptor.get("adapter_version") or adapter_version)
            protocol_versions = list(descriptor.get("protocol_versions") or protocol_versions)
            raw_caps = descriptor.get("capabilities")
            if isinstance(raw_caps, dict):
                declared_caps = dict(raw_caps)
        except Exception:  # noqa: BLE001 — capability probe must fail closed to defaults
            declared_caps = {}
    visual = merge_visual_capabilities(declared_caps)
    formats = visual.get("visual_formats")
    visual_formats = list(formats) if isinstance(formats, list) else []
    roles = sorted(role_procedures)
    procedures = sorted({proc for procs in role_procedures.values() for proc in procs})
    combinations = [
        [role, proc]
        for role, procs in role_procedures.items()
        for proc in procs
    ]
    caps = build_capability_descriptor(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        supported_protocol_versions=protocol_versions,
        supported_roles=roles,
        supported_procedures=procedures,
        isolated_workspace=True,
        cancellation=True,
        progress_events=True,
        structured_output=True,
        command_enforcement=True,
        filesystem_enforcement=True,
        maximum_parallelism=1,
        visual_input=visual.get("visual_input") is True,
        visual_formats=visual_formats,
        pdf=visual.get("pdf") is True,
        svg=visual.get("svg") is True,
        figma_url=visual.get("figma_url") is True,
        screenshot=visual.get("screenshot") is True,
        browser_automation=visual.get("browser_automation") is True,
        viewport_control=visual.get("viewport_control") is True,
        dom_inspection=visual.get("dom_inspection") is True,
        visual_comparison=visual.get("visual_comparison") is True,
    )
    caps["supported_role_procedures"] = combinations
    return caps


def run_governed_execution(
    workspace: Workspace,
    *,
    adapter: Any,
    work_unit: dict[str, Any],
    run_id: str,
    execution_id: str,
    lease_id: str,
    epoch: int,
    role_id: str,
    procedure_id: str,
    base_sha: str,
    grant_allowed_paths: list[str],
    allowed_shell_commands: list[str],
    required_checks: list[str],
    accessible_secrets: list[str] | None = None,
    profile: dict[str, Any] | None = None,
    spi_request: dict[str, Any] | None = None,
    execution_workspace: Path | None = None,
    use_ephemeral_workspace: bool = False,
    run_independent_verification: bool = False,
    instance_id: str = "orchestrator",
    worker_id: str | None = None,
    capabilities: dict[str, Any] | None = None,
    role_procedures: dict[str, set[str]] | None = None,
    known_roles: set[str] | None = None,
    execution_ceiling_paths: list[str] | None = None,
    role_write_paths: list[str] | None = None,
    fence_authoritative_lease: bool = True,
    grant_axis_present: bool = True,
) -> GatewayOutcome:
    """Compile a canonical request and invoke the adapter exclusively via the Gateway.

    Used by the orchestrator tick and supervisor-managed executions. Callers must
    not consume the raw adapter result — only an accepted ``GatewayOutcome``.

    ``role_write_paths`` is normally left unset: when the caller also leaves
    ``known_roles``/``role_procedures`` unset (the real production path, via
    the orchestrator tick), it is derived from the active bundle's
    ``writes.product.paths`` for ``role_id`` and resolved against
    ``work_unit`` with ``resolve_role_write_paths`` (Document 12 §2.2). It
    feeds ``gateway.compile_request()`` (so ``contract.effective_scope`` is
    role-resolved) and ``SpiCompatibleAdapter`` copies that list onto SPI
    ``resolved_scope`` before the Adaptateur runs. See the comment above the
    ``gateway.execute()`` call below for why it is deliberately not also used
    to reject a real commit yet.
    """
    gateway = AgentExecutionGateway(workspace)
    if known_roles is None or role_procedures is None:
        bundle_roles, bundle_pairs, bundle_write_paths = _bundle_role_procedures(workspace)
        compiled_roles = bundle_roles if known_roles is None else set(known_roles)
        compiled_pairs = bundle_pairs if role_procedures is None else role_procedures
        if role_write_paths is None:
            role_write_paths = resolve_role_write_paths(
                bundle_write_paths.get(role_id), work_unit=work_unit
            )
    else:
        compiled_roles = set(known_roles)
        compiled_pairs = role_procedures
    caps = capabilities or _default_capabilities(
        adapter,
        role_procedures=compiled_pairs,
    )
    request, context = gateway.compile_request(
        execution_id=execution_id,
        run_id=run_id,
        work_unit=work_unit,
        lease_id=lease_id,
        epoch=epoch,
        role_id=role_id,
        procedure_id=procedure_id,
        base_sha=base_sha,
        grant_allowed_paths=grant_allowed_paths,
        allowed_shell_commands=allowed_shell_commands,
        required_checks=required_checks,
        capabilities=caps,
        accessible_secrets=accessible_secrets,
        profile=profile,
        known_roles=compiled_roles,
        role_procedures=compiled_pairs,
        adapter_id=str(caps.get("adapter_id") or "external"),
        execution_ceiling_paths=execution_ceiling_paths,
        role_write_paths=role_write_paths,
        grant_axis_present=grant_axis_present,
    )
    bridged = SpiCompatibleAdapter(adapter, spi_request=spi_request or {})
    # role_write_paths is NOT passed to gateway.execute() here. Its post-hoc
    # boundary check (validate_paths_against_scope) classifies files against
    # `inspect_changed_paths(root, base_sha, ...)` — the diff since the Work
    # Unit's own base_sha, shared cumulatively across every lifecycle step
    # (implementation, verification, review, audit), not a per-role/per-step
    # incremental diff. A tests_only role's real files (e.g. only "tests/")
    # would then be checked against files an earlier role already legitimately
    # wrote (e.g. "src/app.py"), producing a false "out-of-role-scope" reject
    # — confirmed via a real regression in
    # test_orchestrator_tick.py::test_tick_walks_a_work_unit_through_verification_review_audit_to_human_test.
    # Enforcing this axis correctly needs a per-role incremental diff (since
    # this role's own execution started), which does not exist yet — a
    # separate increment, not guessed at here. role_write_paths still reaches
    # gateway.compile_request() above, and SpiCompatibleAdapter copies that
    # list onto SPI resolved_scope (Document 12 §2.2 transmission), even
    # though it is not yet used to reject a real commit.
    outcome = gateway.execute(
        request=request,
        adapter=bridged,
        work_unit=work_unit,
        grant_allowed_paths=grant_allowed_paths,
        profile=profile,
        use_ephemeral_workspace=use_ephemeral_workspace,
        execution_workspace=execution_workspace,
        run_independent_verification=run_independent_verification,
        instance_id=instance_id,
        worker_id=worker_id,
        context_package=context,
        fence_authoritative_lease=fence_authoritative_lease,
    )
    for event in outcome.events:
        event_type = str(event.get("event_type") or "")
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type=f"progress:{event_type}",
            run_id=run_id,
            work_unit_id=str(work_unit.get("id") or "") or None,
            payload={
                "useful_progress": is_useful_progress(event_type),
                "execution_id": execution_id,
                "progress_event": event_type,
            },
        )
    return outcome


def accept_via_gateway(
    workspace: Workspace,
    *,
    request: dict[str, Any],
    adapter: Any,
    work_unit: dict[str, Any],
    grant_allowed_paths: list[str],
    profile: dict[str, Any] | None = None,
    instance_id: str,
    use_ephemeral_workspace: bool = True,
    run_independent_verification: bool = False,
    worker_id: str | None = None,
    context_package: dict[str, Any] | None = None,
) -> GatewayOutcome:
    """Accept an adapter execution through the canonical gateway.

    The daemon keeps ownership of leases/epochs/queue; the gateway owns
    contractual validation, evidence provenance, and transactional promotion.
    Prefer ``run_governed_execution`` for the production compile→execute path.
    """
    gateway = AgentExecutionGateway(workspace)
    outcome = gateway.execute(
        request=request,
        adapter=adapter,
        work_unit=work_unit,
        grant_allowed_paths=grant_allowed_paths,
        profile=profile,
        use_ephemeral_workspace=use_ephemeral_workspace,
        run_independent_verification=run_independent_verification,
        instance_id=instance_id,
        worker_id=worker_id,
        context_package=context_package,
    )
    for event in outcome.events:
        event_type = str(event.get("event_type") or "")
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type=f"progress:{event_type}",
            run_id=str(request.get("run_id") or ""),
            work_unit_id=str(request.get("work_unit_id") or "") or None,
            payload={
                "useful_progress": is_useful_progress(event_type),
                "execution_id": request.get("execution_id"),
                "progress_event": event_type,
            },
        )
    return outcome


def useful_progress_event_types() -> frozenset[str]:
    return frozenset(
        item.value
        for item in ProgressEventType
        if is_useful_progress(item)
    )
