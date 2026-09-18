"""Opt-in migration: standalone in-tree install → out-of-tree instance (Document 25).

``--update`` never calls this module (INS-AC-018 / INS-F-014). Operators must
invoke ``tools/migrate_to_instance.py`` explicitly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.errors import InstallationValidationError
from distribution.installer.record import (
    INSTALLATION_RECORD_FILE,
    load_installation_record,
    managed_files_union,
)
from distribution.installer.snapshot import utc_now_iso

AI_TEAM = ".ai-team"
BACKUP_PREFIX = "in-tree-to-instance-"


class InstanceMigrationError(InstallationValidationError):
    """Raised when the opt-in in-tree → instance migration cannot proceed."""


@dataclass(frozen=True)
class MigrationPlan:
    source: Path
    instance: Path
    ensemble_id: str
    member_id: str
    member_kind: str
    instance_id: str
    member_rel_path: str


def _yaml():
    import yaml

    return yaml


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_git_repository(path: Path) -> bool:
    return (path / ".git").exists()


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise InstanceMigrationError(
            "GIT_INIT_FAILED",
            f"cannot git init instance at {path}: {completed.stderr.strip()}",
        )


def _load_profile(ai_team: Path) -> dict[str, Any]:
    path = ai_team / "project-profile.yaml"
    if not path.is_file():
        raise InstanceMigrationError(
            "MISSING_PROFILE",
            f"missing project profile at {path}",
        )
    document = _yaml().safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise InstanceMigrationError("INVALID_PROFILE", f"invalid profile at {path}")
    return document


def _project_id(profile: dict[str, Any]) -> str:
    project = profile.get("project")
    if isinstance(project, dict):
        value = project.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise InstanceMigrationError(
        "MISSING_PROJECT_ID", "project.id is required on the source profile"
    )


def _has_member_link(root: Path) -> bool:
    return (root / AI_TEAM / "member-link.json").is_file()


def _backup_trees(source: Path, backup_root: Path) -> list[str]:
    """Copy whole trees into ``backup_root`` (avoids Windows MAX_PATH nesting)."""
    copied: list[str] = []
    for relative in (AI_TEAM, "scripts", ".cursor", ".claude", "AGENTS.md"):
        src = source / relative
        if not src.exists():
            continue
        dest = backup_root / relative
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        copied.append(relative)
    return copied


def _restore_trees(source: Path, backup_root: Path) -> None:
    for relative in (AI_TEAM, "scripts", ".cursor", ".claude", "AGENTS.md"):
        dest = source / relative
        if dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        src = backup_root / relative
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def os_relpath(target: Path, start: Path) -> str:
    return os.path.relpath(str(target), start=str(start))


def plan_migration(
    *,
    source: Path,
    instance: Path,
    ensemble_id: str,
    member_id: str,
    member_kind: str = "service",
    instance_id: str | None = None,
) -> MigrationPlan:
    source = source.resolve()
    instance = instance.resolve()
    if source == instance:
        raise InstanceMigrationError(
            "SAME_PATH",
            "source and instance directories must differ",
        )
    if not (source / AI_TEAM / "project-profile.yaml").is_file():
        raise InstanceMigrationError(
            "NOT_INSTALLED",
            f"source {source} has no standalone framework install",
        )
    if _has_member_link(source):
        raise InstanceMigrationError(
            "ALREADY_MEMBER",
            f"source {source} already has a member-link; refusing to migrate",
        )
    if not _is_git_repository(source):
        raise InstanceMigrationError(
            "SOURCE_NOT_GIT",
            f"source {source} must be a Git repository (member checkout)",
        )
    record = load_installation_record(source)
    if record is None:
        raise InstanceMigrationError(
            "MISSING_RECORD",
            f"missing installation record under {source / INSTALLATION_RECORD_FILE}",
        )
    if instance.exists() and any(instance.iterdir()):
        raise InstanceMigrationError(
            "INSTANCE_NOT_EMPTY",
            f"instance {instance} must not exist or must be empty",
        )
    profile = _load_profile(source / AI_TEAM)
    _ = _project_id(profile)
    resolved_instance_id = instance_id or instance.name
    member_rel = Path(os_relpath(source, instance)).as_posix()
    return MigrationPlan(
        source=source,
        instance=instance,
        ensemble_id=ensemble_id,
        member_id=member_id,
        member_kind=member_kind,
        instance_id=resolved_instance_id,
        member_rel_path=member_rel,
    )


def _write_yaml(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _yaml().safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _move_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise InstanceMigrationError(
            "DEST_EXISTS",
            f"cannot move {src} onto existing {dest}",
        )
    shutil.move(str(src), str(dest))


def _relocate_project_owned_into_ensemble(instance_ai: Path, ensemble_id: str) -> None:
    ensemble_dir = instance_ai / "ensembles" / ensemble_id
    ensemble_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "state",
        "work-units",
        "evidence",
        "sources",
        "decisions",
        "events",
        "findings",
        "audits",
        "releases",
        "acceptance",
        "human-feedback",
        "notifications",
        "authorizations",
        "context-packages",
        "reconciliation",
        "runs",
        "run-authorization-grants",
        "mission-artifacts",
    ):
        src = instance_ai / name
        if src.exists():
            dest = ensemble_dir / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(src), str(dest))


def _configure_instance_ensemble(plan: MigrationPlan, previous_profile: dict[str, Any]) -> None:
    ai_team = plan.instance / AI_TEAM
    previous_id = _project_id(previous_profile)
    previous_name = previous_id
    project = previous_profile.get("project")
    if isinstance(project, dict) and isinstance(project.get("name"), str):
        previous_name = project["name"]

    instance_profile = dict(previous_profile)
    instance_profile["project"] = {
        **(project if isinstance(project, dict) else {}),
        "id": plan.instance_id,
        "name": plan.instance_id,
    }
    _write_yaml(ai_team / "project-profile.yaml", instance_profile)

    now = utc_now_iso()
    members_doc = {
        "ensemble_id": plan.ensemble_id,
        "status": "registered",
        "revision": 2,
        "members": [
            {
                "id": plan.member_id,
                "kind": plan.member_kind,
                "path": plan.member_rel_path,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    ensemble_dir = ai_team / "ensembles" / plan.ensemble_id
    _write_yaml(ensemble_dir / "members.yaml", members_doc)
    _write_yaml(
        ensemble_dir / "project-profile.yaml",
        {"project": {"id": plan.ensemble_id, "name": previous_name}},
    )
    _relocate_project_owned_into_ensemble(ai_team, plan.ensemble_id)
    state_path = ensemble_dir / "state" / "project-state.yaml"
    if not state_path.is_file():
        _write_yaml(
            state_path,
            {
                "project_id": plan.ensemble_id,
                "constitution_version": "1.4.0",
                "phase": "not_compiled",
                "gates": {
                    "G0": "not_started",
                    "G1": "not_started",
                    "G2": "not_started",
                    "G3": "not_started",
                    "G4": "not_started",
                },
            },
        )
    _write_yaml(
        ai_team / "catalog.yaml",
        {
            "schema_version": 1,
            "instance_id": plan.instance_id,
            "ensembles": [
                {
                    "id": plan.ensemble_id,
                    "status": "registered",
                    "members": [plan.member_id],
                    "previous_standalone_project_id": previous_id,
                }
            ],
        },
    )
    _write_yaml(
        ai_team / "active-ensemble.yaml",
        {"ensemble_id": plan.ensemble_id, "updated_at": now},
    )


def _strip_source_after_move(source: Path) -> None:
    ai_team = source / AI_TEAM
    if ai_team.exists():
        shutil.rmtree(ai_team)
    for relative in ("scripts", ".cursor", ".claude"):
        path = source / relative
        if path.exists():
            shutil.rmtree(path)


def _write_member_overlay(
    member_root: Path,
    *,
    instance_id: str,
    ensemble_id: str,
    member_id: str,
    instance_path: Path,
) -> None:
    """Thin overlay without importing ``member_overlay`` (avoids commands circular import)."""
    from governed_ai.core.persistence.atomic import atomic_write_text

    instance_resolved = instance_path.resolve()
    link_dir = member_root / AI_TEAM
    link_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": 1,
        "instance_id": instance_id,
        "ensemble_id": ensemble_id,
        "member_id": member_id,
        "instance_path": str(instance_resolved),
    }
    atomic_write_text(
        link_dir / "member-link.json",
        json.dumps(document, indent=2) + "\n",
    )
    marker_start = "<!-- governed-ai-member:start -->"
    marker_end = "<!-- governed-ai-member:end -->"
    body = (
        f"This repository is member `{member_id}` of ensemble `{ensemble_id}`.\n"
        "Do not run `/compile-project` or `python scripts/ai-team/gov.py` here.\n"
        "Open the instance and run the client cycle from:\n"
        f"  {instance_resolved}\n"
    )
    wrapped = f"{marker_start}\n{body.rstrip()}\n{marker_end}\n"
    agents_path = member_root / "AGENTS.md"
    if agents_path.is_file():
        existing = agents_path.read_text(encoding="utf-8")
        if marker_start in existing and marker_end in existing:
            start = existing.find(marker_start)
            end = existing.find(marker_end) + len(marker_end)
            text = existing[:start] + wrapped.rstrip() + existing[end:].lstrip("\n")
            if not text.endswith("\n"):
                text += "\n"
            atomic_write_text(agents_path, text)
        else:
            atomic_write_text(agents_path, existing.rstrip() + "\n\n" + wrapped)
    else:
        atomic_write_text(agents_path, wrapped)


def _write_active_code_workspace(instance: Path) -> Path | None:
    """Write ``<ensemble-id>.code-workspace`` for the active ensemble (INS-AC-017)."""
    from governed_ai.core.ensemble_workspace import active_ensemble_folders
    from governed_ai.core.workspace import Workspace

    workspace = Workspace.from_root(instance)
    ensemble_id = workspace.active_ensemble_id
    if not ensemble_id:
        return None
    folders = active_ensemble_folders(workspace)
    document = {
        "folders": [{"name": item["name"], "path": item["path"]} for item in folders],
        "settings": {},
    }
    path = workspace.instance_root / f"{ensemble_id}.code-workspace"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def migrate_in_tree_to_instance(
    *,
    source: Path,
    instance: Path,
    ensemble_id: str,
    member_id: str,
    member_kind: str = "service",
    instance_id: str | None = None,
    dry_run: bool = False,
    fail_after: str | None = None,
) -> dict[str, Any]:
    """Move authoritative install to ``instance`` and leave a thin member link on ``source``."""
    plan = plan_migration(
        source=source,
        instance=instance,
        ensemble_id=ensemble_id,
        member_id=member_id,
        member_kind=member_kind,
        instance_id=instance_id,
    )
    if dry_run:
        return {
            "status": "dry_run",
            "source": str(plan.source),
            "instance": str(plan.instance),
            "ensemble_id": plan.ensemble_id,
            "member_id": plan.member_id,
            "member_path": plan.member_rel_path,
            "instance_id": plan.instance_id,
        }

    previous_profile = _load_profile(plan.source / AI_TEAM)
    # Keep the backup beside the source root so restore survives the .ai-team move
    # and Windows MAX_PATH limits from nested runtime paths.
    backup_root = plan.source / f".{BACKUP_PREFIX}{_now_stamp()}"
    backup_root.mkdir(parents=True, exist_ok=False)
    _backup_trees(plan.source, backup_root)
    (backup_root / "migration-plan.json").write_text(
        json.dumps(
            {
                "created_at": utc_now_iso(),
                "source": str(plan.source),
                "instance": str(plan.instance),
                "ensemble_id": plan.ensemble_id,
                "member_id": plan.member_id,
                "instance_id": plan.instance_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    created_instance = not plan.instance.exists()
    try:
        plan.instance.mkdir(parents=True, exist_ok=True)
        if not _is_git_repository(plan.instance):
            _git_init(plan.instance)
        if fail_after == "snapshot":
            raise InstanceMigrationError("FAILPOINT", "fail_after=snapshot")

        agents = plan.source / "AGENTS.md"
        if agents.is_file():
            shutil.copy2(agents, plan.instance / "AGENTS.md")

        _move_tree(plan.source / AI_TEAM, plan.instance / AI_TEAM)
        _move_tree(plan.source / "scripts", plan.instance / "scripts")
        _move_tree(plan.source / ".cursor", plan.instance / ".cursor")
        _move_tree(plan.source / ".claude", plan.instance / ".claude")
        if fail_after == "move":
            raise InstanceMigrationError("FAILPOINT", "fail_after=move")

        _configure_instance_ensemble(plan, previous_profile)
        if fail_after == "configure":
            raise InstanceMigrationError("FAILPOINT", "fail_after=configure")

        _strip_source_after_move(plan.source)
        _write_member_overlay(
            plan.source,
            instance_id=plan.instance_id,
            ensemble_id=plan.ensemble_id,
            member_id=plan.member_id,
            instance_path=plan.instance,
        )
        if fail_after == "overlay":
            raise InstanceMigrationError("FAILPOINT", "fail_after=overlay")

        code_workspace = _write_active_code_workspace(plan.instance)

        # Persist a zip (short path) under the instance; avoid nested MAX_PATH copies.
        backups_dir = plan.instance / AI_TEAM / "migration-backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        archive_base = backups_dir / backup_root.name.lstrip(".")
        archive = Path(
            shutil.make_archive(str(archive_base), "zip", root_dir=str(backup_root))
        )
        shutil.rmtree(backup_root)
        backup_root = archive
        (backups_dir / f"{archive_base.name}.json").write_text(
            json.dumps(
                {
                    "created_at": utc_now_iso(),
                    "kind": "in_tree_to_instance",
                    "archive": archive.name,
                    "source": str(plan.source),
                    "ensemble_id": plan.ensemble_id,
                    "member_id": plan.member_id,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        if backup_root.is_dir():
            _restore_trees(plan.source, backup_root)
            shutil.rmtree(backup_root, ignore_errors=True)
        if created_instance and plan.instance.exists():
            shutil.rmtree(plan.instance)
        elif plan.instance.exists():
            for name in (AI_TEAM, "scripts", ".cursor", ".claude", "AGENTS.md"):
                path = plan.instance / name
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        raise

    return {
        "status": "migrated",
        "source": str(plan.source),
        "instance": str(plan.instance),
        "ensemble_id": plan.ensemble_id,
        "member_id": plan.member_id,
        "member_path": plan.member_rel_path,
        "instance_id": plan.instance_id,
        "backup_dir": str(backup_root),
        "code_workspace": str(code_workspace) if code_workspace else None,
        "managed_files_count": len(
            managed_files_union(load_installation_record(plan.instance) or {})
        ),
    }
