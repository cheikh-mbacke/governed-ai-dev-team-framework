"""Reconcile design revisions after development has started."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.paths import (
    ensure_design_layout,
    reconciliation_path,
)
from governed_ai.core.design_authority.registry import load_artifact
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReconcileError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def reconcile_design_revision(
    workspace: Workspace,
    *,
    reconciliation_id: str,
    previous_artifact_id: str,
    new_artifact_id: str,
    triggered_by: str,
    persist: bool = True,
) -> dict[str, Any]:
    """Impact analysis when a new authoritative mockup revision is registered.

    Invalidates only conformance evidence tied to the previous artifact.
    Does not rewrite previous contracts; marks affected Work Units for
    reconciliation without blanket invalidation.

    When ``persist=False``, no documents are written to disk; planned mutations
    are returned under ``planned_documents`` for the CommandGateway transaction.
    """
    ensure_design_layout(workspace)
    previous = load_artifact(workspace, previous_artifact_id)
    new = load_artifact(workspace, new_artifact_id)

    affected_work_units: list[str] = []
    invalidated_reports: list[str] = []
    planned_documents: list[dict[str, Any]] = []

    wu_dir = workspace.ai_team / "work-units"
    if wu_dir.is_dir():
        for path in wu_dir.glob("*.yaml"):
            doc = load_yaml(path)
            if not isinstance(doc, dict):
                continue
            binding = doc.get("design_binding") or {}
            contract_id = binding.get("design_contract_id")
            related = False
            if contract_id:
                cpath = workspace.ai_team / "design" / "contracts" / f"{contract_id}.yaml"
                if cpath.is_file():
                    contract = load_yaml(cpath)
                    refs = contract.get("references") if isinstance(contract, dict) else []
                    for ref in refs or []:
                        if ref.get("design_artifact_id") == previous_artifact_id:
                            related = True
                            break
            if related:
                affected_work_units.append(str(doc.get("id") or path.stem))

    conf_dir = workspace.ai_team / "design" / "conformance"
    if conf_dir.is_dir():
        for path in conf_dir.glob("*.yaml"):
            report = load_yaml(path)
            if not isinstance(report, dict):
                continue
            captures = report.get("captures") or []
            tied = any(
                c.get("reference_id") == previous_artifact_id for c in captures if isinstance(c, dict)
            )
            if tied or previous_artifact_id in str(report.get("design_contract_id") or ""):
                report["status"] = "obsolete"
                report["obsolete_reason"] = "design_reference_revised"
                report["obsolete_at"] = _now_iso()
                report["superseded_by_artifact"] = new_artifact_id
                if persist:
                    dump_yaml(path, report)
                else:
                    planned_documents.append({"path": path, "document": report})
                invalidated_reports.append(str(report.get("report_id") or path.stem))

    # Preserve history: never rewrite the previous artifact; mark superseded.
    if previous.get("status") != "superseded":
        previous["status"] = "superseded"
        previous["superseded_by"] = new_artifact_id
        previous["superseded_at"] = _now_iso()
        prev_path = workspace.ai_team / "design" / "artifacts" / f"{previous_artifact_id}.yaml"
        if persist:
            dump_yaml(prev_path, previous)
        else:
            planned_documents.append({"path": prev_path, "document": previous})

    impact: dict[str, Any] = {
        "reconciliation_id": reconciliation_id,
        "schema_version": SCHEMA_VERSION,
        "previous_artifact_id": previous_artifact_id,
        "previous_content_hash": previous.get("content_hash"),
        "new_artifact_id": new_artifact_id,
        "new_content_hash": new.get("content_hash"),
        "triggered_by": triggered_by,
        "created_at": _now_iso(),
        "affected_work_units": affected_work_units,
        "invalidated_conformance_reports": invalidated_reports,
        "unaffected_note": (
            "Work Units without a real relationship to the previous artifact "
            "were not invalidated"
        ),
        "action_required": "design-change-reconciliation",
    }
    impact["impact_hash"] = sha256_canonical(
        {k: v for k, v in impact.items() if k != "impact_hash"}
    )
    if persist:
        dump_yaml(reconciliation_path(workspace, reconciliation_id), impact)
    else:
        planned_documents.append(
            {
                "path": reconciliation_path(workspace, reconciliation_id),
                "document": impact,
            }
        )
        impact["planned_documents"] = planned_documents
    return impact
