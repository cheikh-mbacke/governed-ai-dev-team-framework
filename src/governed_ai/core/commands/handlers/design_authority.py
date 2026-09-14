"""Design Authority command handlers (CommandGateway mutations)."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.design_authority.binding import (
    DesignBindingError,
    bind_design_to_work_unit,
)
from governed_ai.core.design_authority.conformance import (
    ConformanceError,
    run_visual_conformance,
)
from governed_ai.core.design_authority.contract import (
    DesignContractError,
    compile_design_contract,
)
from governed_ai.core.design_authority.reconcile import (
    ReconcileError,
    reconcile_design_revision,
)
from governed_ai.core.design_authority.reference_set import (
    ReferenceSetError,
    create_reference_set,
)
from governed_ai.core.design_authority.registry import (
    DesignRegistryError,
    register_local_artifact,
    register_remote_artifact,
    set_authority_level,
)
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace import Workspace


def _workspace_from_root(workspace_root) -> Workspace:
    if isinstance(workspace_root, Workspace):
        return workspace_root
    return Workspace.from_root(workspace_root.root if hasattr(workspace_root, "root") else workspace_root)


def handle_register_design_artifact(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    artifact_id = payload.get("design_artifact_id")
    if not artifact_id:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA, "design_artifact_id required", "/payload/design_artifact_id"
        )

    workspace = _workspace_from_root(workspace_root)
    human_auth = envelope.get("human_authorization")
    authority = str(payload.get("authority_level") or "advisory")
    registered_by = str(payload.get("registered_by") or envelope["actor"].get("role_id"))

    try:
        if payload.get("source_uri"):
            doc = register_remote_artifact(
                workspace,
                design_artifact_id=str(artifact_id),
                source_uri=str(payload["source_uri"]),
                registered_by=registered_by,
                authority_level=authority,
                source_type=str(payload.get("source_type") or "figma_link"),
                content_pin=payload.get("content_pin"),
                human_authorization=human_auth if isinstance(human_auth, dict) else None,
                allow_figma=bool(payload.get("allow_figma", True)),
                approved_hosts=list(payload.get("approved_hosts") or []),
                screens=list(payload.get("screens") or []),
                components=list(payload.get("components") or []),
                viewports=list(payload.get("viewports") or []),
                states=list(payload.get("states") or []),
                notes=payload.get("notes") if isinstance(payload.get("notes"), dict) else {},
                supersedes=payload.get("supersedes"),
                persist=False,
            )
        else:
            source_path = payload.get("source_path")
            if not source_path:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "source_path or source_uri required",
                    "/payload/source_path",
                )
            doc = register_local_artifact(
                workspace,
                design_artifact_id=str(artifact_id),
                relative_path=str(source_path),
                registered_by=registered_by,
                authority_level=authority,
                source_type=payload.get("source_type"),
                human_authorization=human_auth if isinstance(human_auth, dict) else None,
                screens=list(payload.get("screens") or []),
                components=list(payload.get("components") or []),
                viewports=list(payload.get("viewports") or []),
                states=list(payload.get("states") or []),
                notes=payload.get("notes") if isinstance(payload.get("notes"), dict) else {},
                supersedes=payload.get("supersedes"),
                persist=False,
            )
    except DesignRegistryError as exc:
        code = (
            ErrorCode.HUMAN_AUTH_REQUIRED
            if "human_auth" in exc.code or "self_authorize" in exc.code
            else ErrorCode.INVALID_SCHEMA
        )
        if exc.code == "already_exists":
            code = ErrorCode.ALREADY_EXISTS
        raise GatewayError(code, exc.message, "/payload") from exc

    validate_against_schema(workspace.ai_team, doc, "design-artifact.schema.json")
    # Already persisted by registry; transaction notes the affected entity.
    transaction.plan_yaml_write(
        workspace.ai_team / "design" / "artifacts" / f"{artifact_id}.yaml",
        doc,
    )
    return {"affected": [{"kind": "design_artifact", "id": artifact_id, "document": doc}]}, []


def handle_set_design_artifact_authority(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    human_auth = envelope.get("human_authorization")
    if not isinstance(human_auth, dict):
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required to change design authority",
            "/human_authorization",
        )
    workspace = _workspace_from_root(workspace_root)
    try:
        doc = set_authority_level(
            workspace,
            design_artifact_id=str(payload["design_artifact_id"]),
            authority_level=str(payload["authority_level"]),
            human_authorization=human_auth,
            registered_by=str(payload.get("registered_by") or human_auth.get("granted_by")),
        )
    except DesignRegistryError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, exc.message, "/payload") from exc
    transaction.plan_yaml_write(
        workspace.ai_team / "design" / "artifacts" / f"{payload['design_artifact_id']}.yaml",
        doc,
    )
    return {
        "affected": [{"kind": "design_artifact", "id": payload["design_artifact_id"]}]
    }, []


def handle_create_design_reference_set(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    workspace = _workspace_from_root(workspace_root)
    try:
        doc = create_reference_set(
            workspace,
            design_reference_set_id=str(payload["design_reference_set_id"]),
            title=str(payload.get("title") or payload["design_reference_set_id"]),
            members=list(payload.get("members") or []),
            created_by=str(payload.get("created_by") or envelope["actor"].get("role_id")),
            persist=False,
        )
    except ReferenceSetError as exc:
        code = ErrorCode.ALREADY_EXISTS if exc.code == "already_exists" else ErrorCode.INVALID_SCHEMA
        raise GatewayError(code, exc.message, "/payload") from exc
    validate_against_schema(workspace.ai_team, doc, "design-reference-set.schema.json")
    transaction.plan_yaml_write(
        workspace.ai_team
        / "design"
        / "reference-sets"
        / f"{payload['design_reference_set_id']}.yaml",
        doc,
    )
    return {
        "affected": [
            {"kind": "design_reference_set", "id": payload["design_reference_set_id"]}
        ]
    }, []


def handle_compile_design_contract(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    workspace = _workspace_from_root(workspace_root)
    try:
        doc = compile_design_contract(
            workspace,
            design_contract_id=str(payload["design_contract_id"]),
            design_mode=str(payload["design_mode"]),
            design_reference_set_id=payload.get("design_reference_set_id"),
            authoritative_artifact_ids=list(payload.get("authoritative_artifact_ids") or []),
            compiled_by=str(payload.get("compiled_by") or envelope["actor"].get("role_id")),
            screens=list(payload.get("screens") or []),
            routes=list(payload.get("routes") or []),
            components=list(payload.get("components") or []),
            mandatory_text=list(payload.get("mandatory_text") or []),
            mandatory_elements=list(payload.get("mandatory_elements") or []),
            forbidden_elements=list(payload.get("forbidden_elements") or []),
            states=list(payload.get("states") or []) or None,
            viewports=list(payload.get("viewports") or []) or None,
            tokens=payload.get("tokens") if isinstance(payload.get("tokens"), dict) else None,
            tolerances=payload.get("tolerances")
            if isinstance(payload.get("tolerances"), dict)
            else None,
            free_zones=list(payload.get("free_zones") or []),
            inferences=list(payload.get("inferences") or []),
            conformance_level=str(payload.get("conformance_level") or "tolerant_visual"),
            design_system_precedence=str(
                payload.get("design_system_precedence") or "escalate_on_conflict"
            ),
            persist=False,
        )
    except DesignContractError as exc:
        code = ErrorCode.ALREADY_EXISTS if exc.code == "already_exists" else ErrorCode.INVALID_SCHEMA
        raise GatewayError(code, exc.message, "/payload") from exc
    validate_against_schema(workspace.ai_team, doc, "design-contract.schema.json")
    transaction.plan_yaml_write(
        workspace.ai_team / "design" / "contracts" / f"{payload['design_contract_id']}.yaml",
        doc,
    )
    return {
        "affected": [{"kind": "design_contract", "id": payload["design_contract_id"], "document": doc}]
    }, []


def handle_bind_design_to_work_unit(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    workspace = _workspace_from_root(workspace_root)
    work_unit_id = str(payload.get("work_unit_id") or envelope["target"].get("id"))
    try:
        binding = bind_design_to_work_unit(
            workspace,
            work_unit_id=work_unit_id,
            design_contract_id=payload.get("design_contract_id"),
            design_reference_set_id=payload.get("design_reference_set_id"),
            design_mode=payload.get("design_mode"),
            screens=list(payload.get("screens") or []) or None,
            states=list(payload.get("states") or []) or None,
            conformance_requirements=payload.get("conformance_requirements"),
            persist=False,
        )
    except DesignBindingError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, exc.message, "/payload") from exc
    from datetime import datetime, timezone

    from governed_ai.core.persistence.io import load_yaml

    wu_path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    doc = load_yaml(wu_path)
    if not isinstance(doc, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "Work Unit must be an object", "/payload")
    doc["design_binding"] = binding
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    transaction.plan_yaml_write(wu_path, doc)
    return {
        "affected": [
            {"kind": "work_unit", "id": work_unit_id},
            {"kind": "design_binding", "id": work_unit_id, "binding": binding},
        ]
    }, []


def handle_record_visual_conformance(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    workspace = _workspace_from_root(workspace_root)
    try:
        report = run_visual_conformance(
            workspace,
            report_id=str(payload["report_id"]),
            design_contract_id=str(payload["design_contract_id"]),
            work_unit_id=str(payload["work_unit_id"]),
            commit_sha=str(payload["commit_sha"]),
            verifier_role=str(payload.get("verifier_role") or "visual-qa"),
            implementer_role=payload.get("implementer_role"),
            lease_id=payload.get("lease_id"),
            epoch=payload.get("epoch"),
            expected_lease_id=payload.get("expected_lease_id"),
            expected_epoch=payload.get("expected_epoch"),
            observations=list(payload.get("observations") or []),
            agent_claimed_passed=payload.get("agent_claimed_passed"),
            persist=False,
        )
    except ConformanceError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, exc.message, "/payload") from exc
    validate_against_schema(workspace.ai_team, report, "visual-conformance-report.schema.json")
    transaction.plan_yaml_write(
        workspace.ai_team / "design" / "conformance" / f"{payload['report_id']}.yaml",
        report,
    )
    return {
        "affected": [{"kind": "visual_conformance_report", "id": payload["report_id"]}],
        "report": report,
    }, []


def handle_reconcile_design_revision(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    workspace = _workspace_from_root(workspace_root)
    try:
        impact = reconcile_design_revision(
            workspace,
            reconciliation_id=str(payload["reconciliation_id"]),
            previous_artifact_id=str(payload["previous_artifact_id"]),
            new_artifact_id=str(payload["new_artifact_id"]),
            triggered_by=str(payload.get("triggered_by") or envelope["actor"].get("role_id")),
            persist=False,
        )
    except ReconcileError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, exc.message, "/payload") from exc
    transaction.plan_yaml_write(
        workspace.ai_team
        / "design"
        / "reconciliations"
        / f"{payload['reconciliation_id']}.yaml",
        impact,
    )
    return {
        "affected": [{"kind": "design_reconciliation", "id": payload["reconciliation_id"]}],
        "impact": impact,
    }, []
