"""Active-ensemble folder list and ExecutionRequest member fields (Document 25)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.core.workspace import Workspace


def active_ensemble_folders(workspace: Workspace) -> list[dict[str, str]]:
    """Return instance + declared member folders for the active ensemble only."""
    folders = [
        {
            "name": "instance",
            "path": str(workspace.instance_root),
        }
    ]
    if workspace.active_ensemble_id is None:
        return folders
    for entry in workspace.declared_members():
        member_id = entry["id"]
        folders.append(
            {
                "name": member_id,
                "path": str(workspace.member_root(member_id)),
            }
        )
    return folders


def work_unit_member_id(document: dict[str, Any]) -> str | None:
    value = document.get("member_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def product_work_unit_missing_member_id(workspace: Workspace, document: dict[str, Any]) -> bool:
    if len(workspace.declared_members()) < 2:
        return False
    if document.get("kind") == "integration":
        return False
    return work_unit_member_id(document) is None


def apply_member_execution_fields(
    workspace: Workspace,
    document: dict[str, Any],
    request: dict[str, Any],
) -> None:
    """Add optional SPI ``member_id`` / ``member_root`` (Document 12 additive)."""
    member_id = work_unit_member_id(document)
    if member_id is None:
        return
    request["member_id"] = member_id
    request["member_root"] = str(workspace.member_root(member_id))


def execution_project_root(adapter_root: Path, request: dict[str, Any]) -> Path:
    """Resolve the product tree for an adapter invocation (INS-AC-016)."""
    raw = request.get("execution_workspace")
    if raw:
        return Path(str(raw)).resolve()
    return Path(adapter_root).resolve()
