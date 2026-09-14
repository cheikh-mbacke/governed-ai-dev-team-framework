"""Design Reference Sets — grouped artifacts targeting screens/states/viewports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.paths import (
    ensure_design_layout,
    reference_set_path,
)
from governed_ai.core.design_authority.registry import (
    DesignRegistryError,
    load_artifact,
    verify_artifact_integrity,
)
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReferenceSetError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _target_key(target: dict[str, Any]) -> str:
    parts = [
        str(target.get("route") or ""),
        str(target.get("page") or ""),
        str(target.get("component") or ""),
        str(target.get("journey") or ""),
        str(target.get("state") or ""),
        str(target.get("viewport") or ""),
        str(target.get("theme") or ""),
        str(target.get("platform") or ""),
    ]
    return "|".join(parts)


def create_reference_set(
    workspace: Workspace,
    *,
    design_reference_set_id: str,
    title: str,
    members: list[dict[str, Any]],
    created_by: str,
    persist: bool = True,
) -> dict[str, Any]:
    """Create a reference set after validating members and detecting conflicts."""
    ensure_design_layout(workspace)
    path = reference_set_path(workspace, design_reference_set_id)
    if path.is_file():
        raise ReferenceSetError(
            "already_exists",
            f"reference set {design_reference_set_id!r} already exists",
        )
    issues = validate_reference_members(workspace, members)
    blocking = [i for i in issues if i.get("severity") == "blocking"]
    if blocking:
        raise ReferenceSetError(
            "contradictory_or_invalid_references",
            "reference set contains blocking issues",
            details={"issues": blocking},
        )
    doc = {
        "design_reference_set_id": design_reference_set_id,
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "title": title,
        "created_at": _now_iso(),
        "created_by": created_by,
        "members": members,
        "validation_issues": issues,
        "status": "active",
    }
    doc["set_hash"] = sha256_canonical({k: v for k, v in doc.items() if k != "set_hash"})
    if persist:
        dump_yaml(path, doc)
    return doc


def load_reference_set(workspace: Workspace, design_reference_set_id: str) -> dict[str, Any]:
    path = reference_set_path(workspace, design_reference_set_id)
    if not path.is_file():
        raise ReferenceSetError(
            "not_found", f"reference set {design_reference_set_id!r} not found"
        )
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        raise ReferenceSetError("invalid_reference_set", "reference set must be an object")
    return doc


def validate_reference_members(
    workspace: Workspace, members: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Detect contradictions, duplicates, missing authority, stale hashes."""
    issues: list[dict[str, Any]] = []
    seen_artifacts: dict[str, int] = {}
    authoritative_by_target: dict[str, list[str]] = {}

    for index, member in enumerate(members):
        artifact_id = str(member.get("design_artifact_id") or "")
        target = member.get("target") or {}
        if not artifact_id:
            issues.append(
                {
                    "code": "missing_artifact_id",
                    "severity": "blocking",
                    "member_index": index,
                    "message": "member missing design_artifact_id",
                }
            )
            continue
        try:
            artifact = load_artifact(workspace, artifact_id)
        except DesignRegistryError as exc:
            issues.append(
                {
                    "code": exc.code,
                    "severity": "blocking",
                    "member_index": index,
                    "design_artifact_id": artifact_id,
                    "message": exc.message,
                }
            )
            continue

        status = str(artifact.get("status") or "active")
        authority = str(artifact.get("authority_level") or "advisory")
        if status in {"withdrawn", "superseded"} or authority == "deprecated":
            issues.append(
                {
                    "code": "reference_outdated_or_deprecated",
                    "severity": "blocking" if authority == "authoritative" else "advisory",
                    "member_index": index,
                    "design_artifact_id": artifact_id,
                    "message": f"artifact status={status} authority={authority}",
                }
            )

        integrity = verify_artifact_integrity(workspace, artifact)
        if not integrity.get("ok"):
            severity = "blocking" if authority == "authoritative" else "major"
            issues.append(
                {
                    "code": integrity.get("code") or "integrity_failed",
                    "severity": severity,
                    "member_index": index,
                    "design_artifact_id": artifact_id,
                    "message": integrity.get("message"),
                    "details": integrity,
                }
            )

        seen_artifacts[artifact_id] = seen_artifacts.get(artifact_id, 0) + 1
        key = _target_key(target if isinstance(target, dict) else {})
        if authority == "authoritative":
            authoritative_by_target.setdefault(key, []).append(artifact_id)

    for artifact_id, count in seen_artifacts.items():
        if count > 1:
            issues.append(
                {
                    "code": "duplicate_reference",
                    "severity": "major",
                    "design_artifact_id": artifact_id,
                    "message": f"artifact appears {count} times in the set",
                }
            )

    for key, ids in authoritative_by_target.items():
        unique = sorted(set(ids))
        if len(unique) > 1 and key.strip("|"):
            # Same non-empty target with multiple authoritative artifacts.
            issues.append(
                {
                    "code": "contradictory_authoritative_references",
                    "severity": "blocking",
                    "target_key": key,
                    "design_artifact_ids": unique,
                    "message": "multiple authoritative references cover the same target",
                }
            )

    if not any(
        str((m.get("authority_level") if False else "")) for m in members
    ):
        # Check whether the set has at least one authoritative member when loaded.
        has_auth = False
        for member in members:
            aid = str(member.get("design_artifact_id") or "")
            if not aid:
                continue
            try:
                art = load_artifact(workspace, aid)
            except DesignRegistryError:
                continue
            if art.get("authority_level") == "authoritative" and art.get("status") == "active":
                has_auth = True
                break
        if not has_auth:
            issues.append(
                {
                    "code": "absence_of_authority",
                    "severity": "advisory",
                    "message": "reference set has no active authoritative artifact",
                }
            )

    return issues


def revalidate_reference_set(
    workspace: Workspace, design_reference_set_id: str, *, persist: bool = True
) -> dict[str, Any]:
    doc = load_reference_set(workspace, design_reference_set_id)
    issues = validate_reference_members(workspace, list(doc.get("members") or []))
    doc["validation_issues"] = issues
    doc["revalidated_at"] = _now_iso()
    doc["revision"] = int(doc.get("revision") or 1) + 1
    doc["set_hash"] = sha256_canonical({k: v for k, v in doc.items() if k != "set_hash"})
    if persist:
        dump_yaml(reference_set_path(workspace, design_reference_set_id), doc)
    return doc
