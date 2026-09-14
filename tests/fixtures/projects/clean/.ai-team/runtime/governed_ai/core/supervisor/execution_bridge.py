"""Bridge: Supervisor / orchestrator invoke adapters only via Agent Execution Gateway."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governed_ai.core.execution_gateway.capabilities import build_capability_descriptor
from governed_ai.core.execution_gateway.gateway import (
    AgentExecutionGateway,
    GatewayOutcome,
)
from governed_ai.core.execution_gateway.progress import ProgressEventType, is_useful_progress
from governed_ai.core.supervisor import journal
from governed_ai.core.workspace import Workspace


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
        return self._adapter.execute(merged)


def _bundle_role_procedures(
    workspace: Workspace,
) -> tuple[set[str], dict[str, set[str]]]:
    """Compile real role/procedure attachments from the published active bundle."""
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    known_roles: set[str] = set()
    role_procedures: dict[str, set[str]] = {}
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
    return known_roles, role_procedures


def _default_capabilities(
    adapter: Any,
    *,
    role_procedures: dict[str, set[str]],
) -> dict[str, Any]:
    describe = getattr(adapter, "describe", None)
    adapter_id = "external"
    adapter_version = "1.0.0"
    protocol_versions = ["1.0"]
    if callable(describe):
        try:
            descriptor = describe()
            adapter_id = str(descriptor.get("adapter_id") or adapter_id)
            adapter_version = str(descriptor.get("adapter_version") or adapter_version)
            protocol_versions = list(descriptor.get("protocol_versions") or protocol_versions)
        except Exception:  # noqa: BLE001 — capability probe must fail closed to defaults
            pass
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
    fence_authoritative_lease: bool = True,
    grant_axis_present: bool = True,
) -> GatewayOutcome:
    """Compile a canonical request and invoke the adapter exclusively via the Gateway.

    Used by the orchestrator tick and supervisor-managed executions. Callers must
    not consume the raw adapter result — only an accepted ``GatewayOutcome``.
    """
    gateway = AgentExecutionGateway(workspace)
    if known_roles is None or role_procedures is None:
        bundle_roles, bundle_pairs = _bundle_role_procedures(workspace)
        compiled_roles = bundle_roles if known_roles is None else set(known_roles)
        compiled_pairs = bundle_pairs if role_procedures is None else role_procedures
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
        grant_axis_present=grant_axis_present,
    )
    bridged = SpiCompatibleAdapter(adapter, spi_request=spi_request or {})
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
