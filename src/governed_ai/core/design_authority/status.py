"""Aggregate design authority status for CLI / operators."""

from __future__ import annotations

from typing import Any

from governed_ai.core.design_authority.paths import ensure_design_layout
from governed_ai.core.design_authority.registry import list_artifacts, verify_artifact_integrity
from governed_ai.core.persistence.io import load_yaml
from governed_ai.core.workspace import Workspace


def design_status(workspace: Workspace) -> dict[str, Any]:
    root = ensure_design_layout(workspace)
    artifacts = list_artifacts(workspace)
    integrity = [
        {
            "design_artifact_id": a.get("design_artifact_id"),
            "authority_level": a.get("authority_level"),
            "status": a.get("status"),
            "integrity": verify_artifact_integrity(workspace, a),
        }
        for a in artifacts
    ]
    contracts = []
    for path in sorted((root / "contracts").glob("*.yaml")):
        doc = load_yaml(path)
        if isinstance(doc, dict):
            contracts.append(
                {
                    "design_contract_id": doc.get("design_contract_id"),
                    "design_mode": doc.get("design_mode"),
                    "revision": doc.get("revision"),
                    "contract_hash": doc.get("contract_hash"),
                }
            )
    reference_sets = []
    for path in sorted((root / "reference-sets").glob("*.yaml")):
        doc = load_yaml(path)
        if isinstance(doc, dict):
            reference_sets.append(
                {
                    "design_reference_set_id": doc.get("design_reference_set_id"),
                    "revision": doc.get("revision"),
                    "member_count": len(doc.get("members") or []),
                }
            )
    reports = []
    for path in sorted((root / "conformance").glob("*.yaml")):
        doc = load_yaml(path)
        if isinstance(doc, dict):
            reports.append(
                {
                    "report_id": doc.get("report_id"),
                    "status": doc.get("status"),
                    "blocks_progress": doc.get("blocks_progress"),
                    "work_unit_id": doc.get("work_unit_id"),
                    "commit_sha": doc.get("commit_sha"),
                }
            )
    return {
        "artifact_count": len(artifacts),
        "artifacts": integrity,
        "reference_sets": reference_sets,
        "contracts": contracts,
        "conformance_reports": reports,
    }
