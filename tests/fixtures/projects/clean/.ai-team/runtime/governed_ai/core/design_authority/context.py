"""Multimodal Context Package assembly for design-bound Work Units."""

from __future__ import annotations

from typing import Any

from governed_ai.core.design_authority.contract import load_design_contract, unwrap
from governed_ai.core.design_authority.design_system import load_inventory
from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.reference_set import load_reference_set
from governed_ai.core.design_authority.registry import load_artifact, verify_artifact_integrity
from governed_ai.core.workspace import Workspace


def build_multimodal_design_context(
    workspace: Workspace,
    *,
    work_unit: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the design slice for a Context Package, or None if not applicable."""
    binding = work_unit.get("design_binding")
    if not isinstance(binding, dict) or not binding:
        return None

    contract_id = binding.get("design_contract_id")
    contract = load_design_contract(workspace, str(contract_id)) if contract_id else None
    ref_set_id = binding.get("design_reference_set_id") or (
        contract.get("design_reference_set_id") if contract else None
    )
    ref_set = load_reference_set(workspace, str(ref_set_id)) if ref_set_id else None

    references: list[dict[str, Any]] = []
    for ref in (contract.get("references") if contract else []) or []:
        aid = str(ref.get("design_artifact_id") or "")
        artifact = load_artifact(workspace, aid) if aid else {}
        integrity = verify_artifact_integrity(workspace, artifact) if artifact else {"ok": False}
        references.append(
            {
                "design_artifact_id": aid,
                "authority_level": artifact.get("authority_level"),
                "content_hash": artifact.get("content_hash"),
                "source_path": artifact.get("source_path"),
                "source_uri": artifact.get("source_uri"),
                "verified_accessible": bool(integrity.get("ok")),
                "integrity": integrity,
                "target": ref.get("target") or {},
                # Adapter hint: path must be attached as a real file capability,
                # not merely mentioned in prose.
                "adapter_attachment": {
                    "kind": "workspace_file" if artifact.get("source_path") else "remote_uri",
                    "path": artifact.get("source_path"),
                    "uri": artifact.get("source_uri"),
                    "must_be_readable": artifact.get("authority_level") == "authoritative",
                },
            }
        )

    inventory = load_inventory(workspace)
    free_zones = unwrap(contract.get("free_zones")) if contract else []
    package = {
        "schema_version": SCHEMA_VERSION,
        "design_mode": binding.get("design_mode") or (contract or {}).get("design_mode"),
        "design_contract_id": contract_id,
        "design_contract_hash": (contract or {}).get("contract_hash"),
        "design_contract": contract,
        "design_reference_set_id": ref_set_id,
        "design_reference_set_hash": (ref_set or {}).get("set_hash"),
        "references": references,
        "design_tokens": unwrap(contract.get("tokens")) if contract else {},
        "existing_components": inventory.get("components") or [],
        "design_system_rules": inventory.get("usage_rules") or [],
        "responsive_constraints": unwrap(contract.get("responsive_rules")) if contract else [],
        "states_to_implement": binding.get("states")
        or (unwrap(contract.get("states")) if contract else []),
        "screens": binding.get("screens") or (unwrap(contract.get("screens")) if contract else []),
        "mandatory_text": unwrap(contract.get("mandatory_text")) if contract else [],
        "authority_levels": sorted(
            {str(r.get("authority_level")) for r in references if r.get("authority_level")}
        ),
        "permitted_freedoms": free_zones,
        "expected_visual_evidence_format": {
            "captures": ["reference", "observed", "diff"],
            "dom_snapshot": True,
            "responsive_report": True,
            "accessibility_report": True,
            "token_report": True,
            "divergence_report": True,
            "bind_fields": ["route", "state", "viewport", "reference_id", "commit_sha"],
        },
        "conformance_requirements": binding.get("conformance_requirements") or {},
    }
    package["design_context_hash"] = sha256_canonical(
        {k: v for k, v in package.items() if k != "design_context_hash"}
    )
    return package
