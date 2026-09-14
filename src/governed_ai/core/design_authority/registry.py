"""Design Artifact Registry — governed, versioned visual references."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_bytes, sha256_canonical, sha256_text
from governed_ai.core.design_authority.models import (
    AUTHORITY_LEVELS,
    SCHEMA_VERSION,
)
from governed_ai.core.design_authority.paths import artifact_path, ensure_design_layout
from governed_ai.core.design_authority.security import (
    DesignSecurityError,
    assert_remote_uri_allowed,
    validate_local_artifact,
)
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DesignRegistryError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _require_human_for_authoritative(
    authority_level: str,
    *,
    human_authorization: dict[str, Any] | None,
    registered_by: str,
) -> None:
    if authority_level != "authoritative":
        return
    if not human_authorization:
        raise DesignRegistryError(
            "human_auth_required_for_authoritative",
            "Only an authorized human may assign authority_level=authoritative",
        )
    granted_by = str(human_authorization.get("granted_by") or "").strip()
    if not granted_by:
        raise DesignRegistryError(
            "human_auth_required_for_authoritative",
            "human_authorization.granted_by is required for authoritative artifacts",
        )
    # Agents must not self-proclaim as authoritative authors.
    if registered_by.startswith("agent:") or registered_by.startswith("role:"):
        if granted_by == registered_by:
            raise DesignRegistryError(
                "agent_cannot_self_authorize",
                "agents cannot self-proclaim authoritative design references",
            )


def build_artifact_document(
    *,
    design_artifact_id: str,
    source_type: str,
    registered_by: str,
    authority_level: str = "advisory",
    status: str = "active",
    source_uri: str | None = None,
    source_path: str | None = None,
    content_hash: str,
    created_at: str | None = None,
    registered_at: str | None = None,
    screens: list[str] | None = None,
    components: list[str] | None = None,
    viewports: list[dict[str, Any]] | None = None,
    states: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
    usage_rights: dict[str, Any] | None = None,
    notes: dict[str, Any] | None = None,
    supersedes: str | None = None,
    revision: int = 1,
    frozen_remote: dict[str, Any] | None = None,
    size_bytes: int | None = None,
    mime_type: str | None = None,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    if authority_level not in AUTHORITY_LEVELS:
        raise DesignRegistryError(
            "invalid_authority_level",
            f"unknown authority_level {authority_level!r}",
        )
    now = _now_iso()
    doc: dict[str, Any] = {
        "design_artifact_id": design_artifact_id,
        "schema_version": schema_version,
        "revision": revision,
        "source_type": source_type,
        "content_hash": content_hash,
        "created_at": created_at or now,
        "registered_at": registered_at or now,
        "registered_by": registered_by,
        "authority_level": authority_level,
        "status": status,
        "screens": screens or [],
        "components": components or [],
        "viewports": viewports or [],
        "states": states or [],
        "provenance": provenance
        or {
            "kind": "human" if not registered_by.startswith(("agent:", "role:")) else "external",
            "actor": registered_by,
        },
        "usage_rights": usage_rights or {"constraints": []},
        "notes": notes or {},
    }
    if source_uri:
        doc["source_uri"] = source_uri
    if source_path:
        doc["source_path"] = source_path
    if supersedes:
        doc["supersedes"] = supersedes
    if frozen_remote:
        doc["frozen_remote"] = frozen_remote
    if size_bytes is not None:
        doc["size_bytes"] = size_bytes
    if mime_type:
        doc["mime_type"] = mime_type
    doc["registry_hash"] = sha256_canonical(
        {k: v for k, v in doc.items() if k != "registry_hash"}
    )
    return doc


def register_local_artifact(
    workspace: Workspace,
    *,
    design_artifact_id: str,
    relative_path: str,
    registered_by: str,
    authority_level: str = "advisory",
    source_type: str | None = None,
    human_authorization: dict[str, Any] | None = None,
    screens: list[str] | None = None,
    components: list[str] | None = None,
    viewports: list[dict[str, Any]] | None = None,
    states: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
    usage_rights: dict[str, Any] | None = None,
    notes: dict[str, Any] | None = None,
    supersedes: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    _require_human_for_authoritative(
        authority_level,
        human_authorization=human_authorization,
        registered_by=registered_by,
    )
    ensure_design_layout(workspace)
    path = artifact_path(workspace, design_artifact_id)
    if path.is_file():
        raise DesignRegistryError(
            "already_exists",
            f"design artifact {design_artifact_id!r} already exists",
        )
    try:
        meta = validate_local_artifact(
            workspace.root, relative_path, source_type=source_type
        )
    except DesignSecurityError as exc:
        raise DesignRegistryError(exc.code, exc.message, details=exc.details) from exc

    content_hash = sha256_bytes(meta["content"])
    doc = build_artifact_document(
        design_artifact_id=design_artifact_id,
        source_type=meta["source_type"],
        registered_by=registered_by,
        authority_level=authority_level,
        source_path=relative_path.replace("\\", "/"),
        content_hash=content_hash,
        screens=screens,
        components=components,
        viewports=viewports,
        states=states,
        provenance=provenance,
        usage_rights=usage_rights,
        notes=notes,
        supersedes=supersedes,
        size_bytes=meta["size_bytes"],
        mime_type=meta.get("mime_type"),
    )
    if human_authorization:
        doc["human_authorization"] = {
            "granted_by": human_authorization.get("granted_by"),
            "granted_at": human_authorization.get("granted_at") or _now_iso(),
            "authorization_id": human_authorization.get("authorization_id"),
        }
    if persist:
        dump_yaml(path, doc)
    return doc


def register_remote_artifact(
    workspace: Workspace,
    *,
    design_artifact_id: str,
    source_uri: str,
    registered_by: str,
    authority_level: str = "advisory",
    source_type: str = "figma_link",
    content_pin: str | None = None,
    human_authorization: dict[str, Any] | None = None,
    allow_figma: bool = True,
    approved_hosts: list[str] | None = None,
    screens: list[str] | None = None,
    components: list[str] | None = None,
    viewports: list[dict[str, Any]] | None = None,
    states: list[str] | None = None,
    notes: dict[str, Any] | None = None,
    supersedes: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Register a remote reference. Authoritative remotes MUST be pinned."""
    _require_human_for_authoritative(
        authority_level,
        human_authorization=human_authorization,
        registered_by=registered_by,
    )
    ensure_design_layout(workspace)
    path = artifact_path(workspace, design_artifact_id)
    if path.is_file():
        raise DesignRegistryError(
            "already_exists",
            f"design artifact {design_artifact_id!r} already exists",
        )
    try:
        remote = assert_remote_uri_allowed(
            source_uri, allow_figma=allow_figma, approved_hosts=approved_hosts
        )
    except DesignSecurityError as exc:
        raise DesignRegistryError(exc.code, exc.message, details=exc.details) from exc

    if authority_level == "authoritative" and not content_pin:
        raise DesignRegistryError(
            "remote_must_be_pinned",
            "authoritative remote references require a frozen version/hash pin",
        )
    pin = content_pin or sha256_text(source_uri)
    frozen = {
        "uri": remote["uri"],
        "host": remote["host"],
        "kind": remote["kind"],
        "content_pin": pin,
        "pinned_at": _now_iso(),
    }
    doc = build_artifact_document(
        design_artifact_id=design_artifact_id,
        source_type=source_type if source_type else remote["kind"],
        registered_by=registered_by,
        authority_level=authority_level,
        source_uri=remote["uri"],
        content_hash=pin if content_pin else sha256_text(f"{remote['uri']}|{pin}"),
        screens=screens,
        components=components,
        viewports=viewports,
        states=states,
        notes=notes,
        supersedes=supersedes,
        frozen_remote=frozen,
    )
    if human_authorization:
        doc["human_authorization"] = {
            "granted_by": human_authorization.get("granted_by"),
            "granted_at": human_authorization.get("granted_at") or _now_iso(),
            "authorization_id": human_authorization.get("authorization_id"),
        }
    if persist:
        dump_yaml(path, doc)
    return doc


def load_artifact(workspace: Workspace, design_artifact_id: str) -> dict[str, Any]:
    path = artifact_path(workspace, design_artifact_id)
    if not path.is_file():
        raise DesignRegistryError(
            "not_found", f"design artifact {design_artifact_id!r} not found"
        )
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        raise DesignRegistryError("invalid_artifact", "artifact document must be an object")
    return doc


def verify_artifact_integrity(workspace: Workspace, artifact: dict[str, Any]) -> dict[str, Any]:
    """Recompute hash for local sources; detect post-approval mutation."""
    source_path = artifact.get("source_path")
    if source_path:
        try:
            meta = validate_local_artifact(
                workspace.root,
                str(source_path),
                source_type=str(artifact.get("source_type") or None),
            )
        except DesignSecurityError as exc:
            return {
                "ok": False,
                "code": exc.code,
                "message": exc.message,
                "authority_level": artifact.get("authority_level"),
            }
        actual = sha256_bytes(meta["content"])
        expected = str(artifact.get("content_hash") or "")
        if actual != expected:
            return {
                "ok": False,
                "code": "reference_modified_after_approval",
                "message": "local design reference content hash changed after registration",
                "expected": expected,
                "actual": actual,
                "authority_level": artifact.get("authority_level"),
            }
        return {"ok": True, "content_hash": actual}

    frozen = artifact.get("frozen_remote") or {}
    if artifact.get("source_uri") and frozen.get("content_pin"):
        # Remote content is considered intact when the pin recorded at approval
        # is still present. Live re-download is intentionally not performed here.
        return {
            "ok": True,
            "content_hash": artifact.get("content_hash"),
            "pin": frozen.get("content_pin"),
            "limitation": "remote_pin_checked_not_redownloaded",
        }
    if artifact.get("source_uri") and not frozen.get("content_pin"):
        return {
            "ok": False,
            "code": "remote_unpinned",
            "message": "remote design reference has no frozen pin",
            "authority_level": artifact.get("authority_level"),
        }
    return {
        "ok": False,
        "code": "unverifiable_artifact",
        "message": "artifact has neither local path nor pinned remote URI",
    }


def list_artifacts(workspace: Workspace) -> list[dict[str, Any]]:
    root = ensure_design_layout(workspace) / "artifacts"
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        doc = load_yaml(path)
        if isinstance(doc, dict):
            items.append(doc)
    return items


def set_authority_level(
    workspace: Workspace,
    *,
    design_artifact_id: str,
    authority_level: str,
    human_authorization: dict[str, Any],
    registered_by: str,
) -> dict[str, Any]:
    """Only humans may raise/lower to or from authoritative."""
    if authority_level not in AUTHORITY_LEVELS:
        raise DesignRegistryError(
            "invalid_authority_level",
            f"unknown authority_level {authority_level!r}",
        )
    doc = load_artifact(workspace, design_artifact_id)
    previous = doc.get("authority_level")
    if authority_level == "authoritative" or previous == "authoritative":
        _require_human_for_authoritative(
            "authoritative",
            human_authorization=human_authorization,
            registered_by=registered_by,
        )
    doc["authority_level"] = authority_level
    doc["revision"] = int(doc.get("revision") or 1) + 1
    doc["updated_at"] = _now_iso()
    doc["human_authorization"] = {
        "granted_by": human_authorization.get("granted_by"),
        "granted_at": human_authorization.get("granted_at") or _now_iso(),
        "authorization_id": human_authorization.get("authorization_id"),
        "previous_authority_level": previous,
    }
    doc["registry_hash"] = sha256_canonical(
        {k: v for k, v in doc.items() if k != "registry_hash"}
    )
    dump_yaml(artifact_path(workspace, design_artifact_id), doc)
    return doc
