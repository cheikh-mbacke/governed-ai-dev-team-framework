"""Relocate legacy v0.6.x installed paths to Document 11 §4 layout."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from distribution.installer.paths import (
    FORENSIC_REVIEW_PATHS,
    RELOCATED_COPY_PREFIXES,
)
from distribution.installer.record import normalize_path


@dataclass(frozen=True)
class LayoutMigrationResult:
    moved: list[tuple[str, str]]
    obsolete: list[str]
    forensic_paths: list[str]
    forensic_events: list[Path]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _emit_forensic_event(target: Path, paths: list[str], *, version_from: str, version_to: str) -> Path:
    timestamp = datetime.now(timezone.utc)
    event_id = f"EVT-{timestamp:%Y%m%dT%H%M%SZ}-LAYOUT-FORENSIC-REVIEW"
    events_dir = target / ".ai-team" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / f"{event_id}.yaml"
    summary = (
        f"Framework layout migration {version_from} -> {version_to} requires human review "
        f"for ambiguous root files: {', '.join(paths)}. These files were not moved or "
        "modified automatically because a prior install may have silently overwritten "
        "project-owned content and no historical content hash is available."
    )
    details_paths = "\n".join(f"  - {item}" for item in paths)
    content = (
        f"id: {event_id}\n"
        "type: DECISION_REQUEST\n"
        "work_unit: null\n"
        f"created_at: '{timestamp.isoformat(timespec='seconds')}'\n"
        "created_by_role: distribution\n"
        f"summary: >-\n  {summary}\n"
        "details:\n"
        f"  migration: layout_{version_from}_to_{version_to}\n"
        f"  paths:\n{details_paths}\n"
        "  recommended_actions:\n"
        "    - Compare each path with project intent and version control history\n"
        "    - Merge or relocate manually if the file is project-owned\n"
        "    - Remove framework-managed remnants if confirmed safe\n"
        "affected_nodes: []\n"
        "requires_human: true\n"
        "status: open\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def iter_legacy_migration_destination_files(target: Path) -> list[Path]:
    """Destination file paths a pending layout migration would create.

    Computed from the legacy source tree without requiring the migration to
    have run yet, so callers can snapshot these paths for rollback before
    the copy happens.
    """
    destinations: list[Path] = []
    for src_prefix, dest_prefix in RELOCATED_COPY_PREFIXES:
        legacy = target / src_prefix
        dest = target / dest_prefix
        if not legacy.is_dir() or dest.exists():
            continue
        for path in legacy.rglob("*"):
            if path.is_file():
                destinations.append(dest / path.relative_to(legacy))
    return destinations


def remove_migrated_legacy_paths(target: Path, moved: list[tuple[str, str]]) -> None:
    """Delete legacy source directories once the migration is fully committed.

    Must only be called after the whole update transaction has succeeded —
    the legacy directories are the last safety net if a later step fails.
    """
    for src_prefix, _dest_prefix in moved:
        legacy = target / src_prefix
        if legacy.is_dir():
            shutil.rmtree(legacy)


def plan_layout_migration(target: Path) -> LayoutMigrationResult:
    moved: list[tuple[str, str]] = []
    obsolete: list[str] = []
    forensic: list[Path] = []

    for src_prefix, dest_prefix in RELOCATED_COPY_PREFIXES:
        legacy = target / src_prefix
        dest = target / dest_prefix
        if legacy.exists() and legacy.is_dir():
            if not dest.exists():
                moved.append((src_prefix, dest_prefix))
            else:
                obsolete.append(src_prefix)

    for ambiguous in sorted(FORENSIC_REVIEW_PATHS):
        if (target / ambiguous).exists():
            forensic.append(ambiguous)

    return LayoutMigrationResult(moved=moved, obsolete=obsolete, forensic_paths=forensic, forensic_events=[])


def apply_layout_migration(
    target: Path,
    *,
    version_from: str = "0.6.0",
    version_to: str = "0.7.0",
    dry_run: bool = False,
) -> LayoutMigrationResult:
    plan = plan_layout_migration(target)
    if dry_run:
        return plan

    for src_prefix, dest_prefix in plan.moved:
        legacy = target / src_prefix
        dest = target / dest_prefix
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        # Copy (not move): the legacy directory is only deleted by
        # remove_migrated_legacy_paths(), after the caller confirms the
        # whole update transaction succeeded. This keeps a failure anywhere
        # downstream (validation, constitution migration, ...) recoverable
        # without losing the pre-migration layout.
        shutil.copytree(str(legacy), str(dest))

    emitted: list[Path] = []
    ambiguous_existing = [p for p in plan.forensic_paths if (target / p).exists()]
    if ambiguous_existing:
        emitted.append(
            _emit_forensic_event(
                target,
                ambiguous_existing,
                version_from=version_from,
                version_to=version_to,
            )
        )

    obsolete = list(plan.obsolete)
    for src_prefix, _dest in RELOCATED_COPY_PREFIXES:
        legacy = target / src_prefix
        if legacy.exists() and normalize_path(src_prefix) not in {m[0] for m in plan.moved}:
            obsolete.append(src_prefix)

    return LayoutMigrationResult(
        moved=plan.moved,
        obsolete=sorted(set(obsolete)),
        forensic_paths=plan.forensic_paths,
        forensic_events=emitted,
    )
