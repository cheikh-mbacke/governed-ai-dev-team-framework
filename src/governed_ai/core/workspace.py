"""Project workspace paths without script-relative discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AI_TEAM_DIR_NAME = ".ai-team"
FABRIC_DIR_NAME = ".fabric"
MEMBER_LINK_NAME = "member-link.json"
PAYLOAD_AI_TEAM_REL = Path("distribution") / "payload" / ".ai-team"
CATALOG_REL = Path("catalog.yaml")
ENSEMBLES_DIR_NAME = "ensembles"
MEMBERS_FILE_NAME = "members.yaml"
ACTIVE_ENSEMBLE_FILE = "active-ensemble.yaml"


class WorkspaceError(RuntimeError):
    """Invalid instance, member-link, or ensemble member resolution."""


@dataclass(frozen=True, slots=True)
class Workspace:
    """Resolved instance root and derived governance paths.

    Standalone (0.7.x): ``root`` is the installed product Git root, and
    ``instance_root`` equals ``member_root()``. Hors-arbre (Document 25):
    ``root`` is the instance directory; members live at other local paths.
    """

    root: Path
    active_ensemble_id: str | None = None
    discovered_member_id: str | None = None

    @property
    def instance_root(self) -> Path:
        return self.root

    @property
    def fabric(self) -> Path | None:
        path = self.root / FABRIC_DIR_NAME
        return path if path.is_dir() else None

    @property
    def profile_path(self) -> Path:
        fabric_profile = self.root / FABRIC_DIR_NAME / "project-profile.yaml"
        if fabric_profile.is_file():
            return fabric_profile
        return self.root / AI_TEAM_DIR_NAME / "project-profile.yaml"

    @property
    def ai_team(self) -> Path:
        """Governance payload tree: payload depot on fabrication, `.ai-team/` on clients."""
        if (self.root / FABRIC_DIR_NAME / "project-profile.yaml").is_file():
            payload = self.root / PAYLOAD_AI_TEAM_REL
            if payload.is_dir():
                return payload
        return self.root / AI_TEAM_DIR_NAME

    @property
    def catalog_path(self) -> Path:
        return self.ai_team / CATALOG_REL

    @property
    def ensembles_root(self) -> Path:
        return self.ai_team / ENSEMBLES_DIR_NAME

    @property
    def ensemble_dir(self) -> Path | None:
        if self.active_ensemble_id is None:
            return None
        return self.ensembles_root / self.active_ensemble_id

    @property
    def ensemble_members_path(self) -> Path | None:
        directory = self.ensemble_dir
        if directory is None:
            return None
        return directory / MEMBERS_FILE_NAME

    def member_root(self, member_id: str | None = None) -> Path:
        """Return the Git root to execute against.

        Standalone (no ensemble / no members file): the instance root.
        Hors-arbre: the declared ``path`` of ``member_id`` or
        ``discovered_member_id``.
        """
        target_id = member_id if member_id is not None else self.discovered_member_id
        if target_id is None or self.active_ensemble_id is None:
            return self.root
        members_path = self.ensemble_members_path
        if members_path is None or not members_path.is_file():
            return self.root
        entry = _member_entry(members_path, target_id)
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise WorkspaceError(f"ensemble member {target_id!r} is missing path")
        resolved = _resolve_member_path(self.root, raw_path)
        if resolved == self.root:
            raise WorkspaceError(
                f"ensemble member {target_id!r} path must not be the instance root"
            )
        return resolved

    @classmethod
    def from_root(cls, root: Path | str) -> Workspace:
        resolved = Path(root).resolve()
        return cls(
            root=resolved,
            active_ensemble_id=_read_active_ensemble_id(resolved / AI_TEAM_DIR_NAME),
        )

    @classmethod
    def discover(cls, start: Path | str) -> Workspace:
        """Walk upward until a fabrication, member-link, or client root is found.

        A ``member-link.json`` is resolved to the instance directory (Document 25).
        Standalone clients with a full `.ai-team/` and no link keep 0.7.x behavior.
        """
        current = Path(start).resolve()
        if current.is_file():
            current = current.parent
        while True:
            if (current / FABRIC_DIR_NAME / "project-profile.yaml").is_file():
                return cls(root=current)
            link_path = current / AI_TEAM_DIR_NAME / MEMBER_LINK_NAME
            if link_path.is_file():
                return cls._from_member_link(link_path, current)
            if (current / AI_TEAM_DIR_NAME).is_dir():
                return cls(
                    root=current,
                    active_ensemble_id=_read_active_ensemble_id(current / AI_TEAM_DIR_NAME),
                )
            parent = current.parent
            if parent == current:
                msg = (
                    f"Could not find {FABRIC_DIR_NAME} or {AI_TEAM_DIR_NAME} "
                    f"directory walking up from {start}"
                )
                raise FileNotFoundError(msg)
            current = parent

    @classmethod
    def _from_member_link(cls, link_path: Path, member_root: Path) -> Workspace:
        try:
            payload = json.loads(link_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"invalid member-link at {link_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise WorkspaceError(f"member-link at {link_path} must be an object")
        instance_path = payload.get("instance_path")
        ensemble_id = payload.get("ensemble_id")
        member_id = payload.get("member_id")
        if not isinstance(instance_path, str) or not instance_path.strip():
            raise WorkspaceError(f"member-link at {link_path} is missing instance_path")
        if not isinstance(ensemble_id, str) or not ensemble_id:
            raise WorkspaceError(f"member-link at {link_path} is missing ensemble_id")
        if not isinstance(member_id, str) or not member_id:
            raise WorkspaceError(f"member-link at {link_path} is missing member_id")
        instance = Path(instance_path)
        if not instance.is_absolute():
            instance = (member_root / instance).resolve()
        else:
            instance = instance.resolve()
        if instance == member_root:
            raise WorkspaceError("member-link instance_path must not resolve to the member root")
        if not (instance / AI_TEAM_DIR_NAME).is_dir() and not (
            instance / FABRIC_DIR_NAME / "project-profile.yaml"
        ).is_file():
            raise FileNotFoundError(
                f"member-link instance_path does not contain {AI_TEAM_DIR_NAME}: {instance}"
            )
        return cls(
            root=instance,
            active_ensemble_id=ensemble_id,
            discovered_member_id=member_id,
        )


def _read_active_ensemble_id(ai_team: Path) -> str | None:
    path = ai_team / ACTIVE_ENSEMBLE_FILE
    if not path.is_file():
        return None
    try:
        import yaml
    except ModuleNotFoundError:
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(document, dict):
        return None
    value = document.get("ensemble_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _member_entry(members_path: Path, member_id: str) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise WorkspaceError("PyYAML is required to resolve ensemble members") from exc
    try:
        document = yaml.safe_load(members_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise WorkspaceError(f"cannot read ensemble members at {members_path}: {exc}") from exc
    if not isinstance(document, dict):
        raise WorkspaceError(f"ensemble members at {members_path} must be an object")
    for entry in document.get("members") or []:
        if isinstance(entry, dict) and entry.get("id") == member_id:
            return entry
    raise WorkspaceError(f"ensemble member {member_id!r} is not declared in {members_path}")


def _resolve_member_path(instance_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (instance_root / candidate).resolve()
