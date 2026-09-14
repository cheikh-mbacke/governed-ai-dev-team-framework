"""Work Unit ↔ Design Contract binding and G1 readiness checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.contract import (
    DesignContractError,
    load_design_contract,
    unwrap,
)
from governed_ai.core.design_authority.models import DESIGN_MODES
from governed_ai.core.design_authority.reference_set import (
    ReferenceSetError,
    load_reference_set,
    validate_reference_members,
)
from governed_ai.core.design_authority.registry import load_artifact, verify_artifact_integrity
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace

UI_ZONES = frozenset({"frontend", "fullstack", "mobile"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DesignBindingError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def default_design_mode_for_work_unit(
    workspace: Workspace,
    work_unit: dict[str, Any],
    *,
    requested_mode: str | None = None,
    design_contract_id: str | None = None,
    design_reference_set_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve design_mode with silent-ignore prevention.

    Returns (mode, clarification_or_decision_issues).
    """
    issues: list[dict[str, Any]] = []
    area = str((work_unit.get("zone") or {}).get("area") or "").lower()
    if area not in UI_ZONES:
        return requested_mode or "maintain", issues

    auth_ids: list[str] = []
    if design_reference_set_id:
        ref_set = load_reference_set(workspace, design_reference_set_id)
        members = list(ref_set.get("members") or [])
        member_issues = validate_reference_members(workspace, members)
        if any(i.get("code") == "contradictory_authoritative_references" for i in member_issues):
            issues.append(
                {
                    "code": "g1_blocked_contradictory_design",
                    "severity": "blocking",
                    "message": "contradictory authoritative design references block G1",
                    "issues": member_issues,
                }
            )
        for member in members:
            aid = str(member.get("design_artifact_id") or "")
            if not aid:
                continue
            art = load_artifact(workspace, aid)
            if art.get("authority_level") == "authoritative" and art.get("status") == "active":
                auth_ids.append(aid)

    if design_contract_id:
        contract = load_design_contract(workspace, design_contract_id)
        for ref in contract.get("references") or []:
            if ref.get("authority_level") == "authoritative":
                auth_ids.append(str(ref.get("design_artifact_id")))

    auth_ids = sorted(set(auth_ids))
    if requested_mode == "create" and auth_ids:
        issues.append(
            {
                "code": "human_decision_required",
                "severity": "blocking",
                "message": (
                    "create requested while authoritative design exists; "
                    "human decision required"
                ),
                "authoritative_artifact_ids": auth_ids,
            }
        )
        return "create", issues

    if requested_mode and requested_mode in DESIGN_MODES:
        if requested_mode in {"create", "explore"} and auth_ids:
            # Already handled above for create; explore with auth refs also needs decision.
            issues.append(
                {
                    "code": "human_decision_required",
                    "severity": "blocking",
                    "message": (
                        f"{requested_mode} requested while authoritative design exists"
                    ),
                    "authoritative_artifact_ids": auth_ids,
                }
            )
        return requested_mode, issues

    if auth_ids:
        return "conform", issues
    return "create", issues


def bind_design_to_work_unit(
    workspace: Workspace,
    *,
    work_unit_id: str,
    design_contract_id: str | None = None,
    design_reference_set_id: str | None = None,
    design_mode: str | None = None,
    screens: list[str] | None = None,
    states: list[str] | None = None,
    conformance_requirements: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    wu_path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    if not wu_path.is_file():
        raise DesignBindingError("work_unit_not_found", f"Work Unit {work_unit_id!r} not found")
    work_unit = load_yaml(wu_path)
    if not isinstance(work_unit, dict):
        raise DesignBindingError("invalid_work_unit", "Work Unit must be an object")

    if design_contract_id:
        try:
            contract = load_design_contract(workspace, design_contract_id)
        except DesignContractError as exc:
            raise DesignBindingError(exc.code, exc.message, details=exc.details) from exc
        if design_reference_set_id is None:
            design_reference_set_id = contract.get("design_reference_set_id")
        if design_mode is None:
            design_mode = str(contract.get("design_mode"))
        if screens is None:
            screens = list(unwrap(contract.get("screens")) or [])
        if states is None:
            states = list(unwrap(contract.get("states")) or [])

    mode, issues = default_design_mode_for_work_unit(
        workspace,
        work_unit,
        requested_mode=design_mode,
        design_contract_id=design_contract_id,
        design_reference_set_id=design_reference_set_id,
    )
    blocking = [i for i in issues if i.get("severity") == "blocking"]
    if blocking:
        raise DesignBindingError(
            blocking[0]["code"],
            blocking[0]["message"],
            details={"issues": issues},
        )

    binding = {
        "design_contract_id": design_contract_id,
        "design_reference_set_id": design_reference_set_id,
        "design_mode": mode,
        "screens": screens or [],
        "states": states or [],
        "conformance_requirements": conformance_requirements
        or {
            "blocking_divergences_block_progress": True,
            "require_multi_viewport": True,
            "require_required_states": True,
            "require_accessibility": True,
        },
        "bound_at": _now_iso(),
        "issues": issues,
    }
    work_unit["design_binding"] = binding
    work_unit["updated_at"] = _now_iso()
    if persist:
        dump_yaml(wu_path, work_unit)
    return binding


def evaluate_g1_design_readiness(
    workspace: Workspace, work_unit: dict[str, Any]
) -> dict[str, Any]:
    """G1 check: exploitable Design Contract when UI WU requires conform/adapt."""
    area = str((work_unit.get("zone") or {}).get("area") or "").lower()
    if area not in UI_ZONES:
        return {"ok": True, "applicable": False, "issues": []}

    binding = work_unit.get("design_binding") or {}
    mode = str(binding.get("design_mode") or "")
    issues: list[dict[str, Any]] = []

    # Detect ignored authoritative artifacts registered for matching screens.
    # Without a binding, scan reference sets is out of scope; require binding
    # only when mode is conform/adapt or contract id is present.
    contract_id = binding.get("design_contract_id")
    if mode in {"conform", "adapt"} or contract_id:
        if not contract_id:
            issues.append(
                {
                    "code": "missing_design_contract",
                    "severity": "blocking",
                    "message": "UI Work Unit in conform/adapt requires a Design Contract",
                }
            )
        else:
            try:
                contract = load_design_contract(workspace, str(contract_id))
            except DesignContractError as exc:
                issues.append(
                    {
                        "code": exc.code,
                        "severity": "blocking",
                        "message": exc.message,
                    }
                )
                return {"ok": False, "applicable": True, "issues": issues}

            for ref in contract.get("references") or []:
                if ref.get("authority_level") != "authoritative":
                    continue
                aid = str(ref.get("design_artifact_id") or "")
                try:
                    artifact = load_artifact(workspace, aid)
                except Exception as exc:  # noqa: BLE001
                    issues.append(
                        {
                            "code": "authoritative_reference_missing",
                            "severity": "blocking",
                            "design_artifact_id": aid,
                            "message": str(exc),
                        }
                    )
                    continue
                integrity = verify_artifact_integrity(workspace, artifact)
                if not integrity.get("ok"):
                    issues.append(
                        {
                            "code": integrity.get("code") or "integrity_failed",
                            "severity": "blocking",
                            "design_artifact_id": aid,
                            "message": integrity.get("message"),
                        }
                    )

            ref_set_id = binding.get("design_reference_set_id") or contract.get(
                "design_reference_set_id"
            )
            if ref_set_id:
                try:
                    ref_set = load_reference_set(workspace, str(ref_set_id))
                    member_issues = validate_reference_members(
                        workspace, list(ref_set.get("members") or [])
                    )
                    for item in member_issues:
                        if item.get("code") == "contradictory_authoritative_references":
                            issues.append({**item, "severity": "blocking"})
                except ReferenceSetError as exc:
                    issues.append(
                        {
                            "code": exc.code,
                            "severity": "blocking",
                            "message": exc.message,
                        }
                    )

    ok = not any(i.get("severity") == "blocking" for i in issues)
    return {"ok": ok, "applicable": True, "issues": issues, "design_mode": mode}
