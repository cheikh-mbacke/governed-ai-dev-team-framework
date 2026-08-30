"""Installation snapshot and rollback (Document 13 §11)."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from distribution.installer.build_record import utc_now_iso


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


@dataclass(frozen=True)
class SnapshotEntry:
    path: str
    sha256: str
    owner: str | None = None


@dataclass
class InstallationSnapshot:
    created_at: str
    entries: list[SnapshotEntry]
    manifest_path: Path
    existing_paths: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "entries": [
                {"path": entry.path, "sha256": entry.sha256, "owner": entry.owner}
                for entry in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], manifest_path: Path) -> InstallationSnapshot:
        entries = [
            SnapshotEntry(
                path=str(item["path"]),
                sha256=str(item["sha256"]),
                owner=str(item["owner"]) if item.get("owner") else None,
            )
            for item in data.get("entries") or []
            if isinstance(item, dict)
        ]
        return cls(
            created_at=str(data.get("created_at", "")),
            entries=entries,
            manifest_path=manifest_path,
            existing_paths={entry.path for entry in entries},
        )


def _owner_for_path(path: str) -> str | None:
    try:
        from distribution.installer.ownership import classify_managed_file

        return classify_managed_file(path)
    except ValueError:
        return None


def create_snapshot(
    target: Path,
    paths: list[Path],
    backup_root: Path,
) -> InstallationSnapshot:
    created_at = utc_now_iso()
    entries: list[SnapshotEntry] = []
    existing: set[str] = set()

    for path in paths:
        relative = path.relative_to(target)
        rel_posix = relative.as_posix()
        if path.exists() and path.is_file():
            existing.add(rel_posix)
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            entries.append(
                SnapshotEntry(
                    path=rel_posix,
                    sha256=sha256_file(path),
                    owner=_owner_for_path(rel_posix),
                )
            )

    manifest_path = backup_root / "snapshot-manifest.json"
    snapshot = InstallationSnapshot(
        created_at=created_at,
        entries=entries,
        manifest_path=manifest_path,
        existing_paths=existing,
    )
    manifest_path.write_text(
        json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return snapshot


def rollback_paths(
    paths: list[Path],
    existing: set[str],
    target: Path,
    backup_root: Path,
) -> None:
    for path in sorted(set(paths), key=lambda item: len(item.parts), reverse=True):
        relative = path.relative_to(target)
        rel_posix = relative.as_posix()
        if rel_posix in existing:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_root / relative, path)
        elif path.exists() and path.is_file():
            path.unlink()


def restore_snapshot(snapshot: InstallationSnapshot, target: Path, backup_root: Path) -> None:
    existing = snapshot.existing_paths
    touched = [target / entry.path for entry in snapshot.entries]
    rollback_paths(touched, existing, target, backup_root)

    for entry in snapshot.entries:
        restored = target / entry.path
        if restored.is_file():
            current = sha256_file(restored)
            if current != entry.sha256:
                raise RuntimeError(
                    f"rollback hash mismatch for {entry.path}: expected {entry.sha256}, got {current}"
                )


def load_snapshot_manifest(backup_root: Path) -> InstallationSnapshot:
    manifest_path = backup_root / "snapshot-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("snapshot manifest root must be an object")
    return InstallationSnapshot.from_dict(data, manifest_path)
