"""Workspace layout helpers for Design Authority state."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.workspace import Workspace


def design_root(workspace: Workspace | Path) -> Path:
    root = workspace.ai_team if isinstance(workspace, Workspace) else Path(workspace)
    return root / "design"


def ensure_design_layout(workspace: Workspace | Path) -> Path:
    root = design_root(workspace)
    for relative in (
        "artifacts",
        "artifacts/blobs",
        "reference-sets",
        "contracts",
        "system",
        "conformance",
        "evidence",
        "reconciliations",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def artifact_path(workspace: Workspace | Path, design_artifact_id: str) -> Path:
    return design_root(workspace) / "artifacts" / f"{design_artifact_id}.yaml"


def reference_set_path(workspace: Workspace | Path, reference_set_id: str) -> Path:
    return design_root(workspace) / "reference-sets" / f"{reference_set_id}.yaml"


def contract_path(workspace: Workspace | Path, design_contract_id: str) -> Path:
    return design_root(workspace) / "contracts" / f"{design_contract_id}.yaml"


def conformance_path(workspace: Workspace | Path, report_id: str) -> Path:
    return design_root(workspace) / "conformance" / f"{report_id}.yaml"


def inventory_path(workspace: Workspace | Path) -> Path:
    return design_root(workspace) / "system" / "inventory.yaml"


def reconciliation_path(workspace: Workspace | Path, reconciliation_id: str) -> Path:
    return design_root(workspace) / "reconciliations" / f"{reconciliation_id}.yaml"


def evidence_dir(workspace: Workspace | Path, evidence_id: str) -> Path:
    return design_root(workspace) / "evidence" / evidence_id
