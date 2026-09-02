"""Fresh install and transactional update operations."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from distribution.installer.apply import apply_copy_entries, collect_changed_destinations
from distribution.installer.errors import InstallationValidationError
from distribution.installer.build_record import (
    finalize_installation_manifests,
    validate_installation_record,
)
from distribution.installer.version_policy import validate_update_path
from distribution.installer.collisions import (
    format_collision_report,
    scan_fresh_install_collisions,
    scan_local_drift_collisions,
)
from distribution.installer.constants import PROJECT_OWNED_PATTERNS
from distribution.installer.fabrication_layout import (
    FRESH_PROJECT_SEED_SOURCES,
    source_constitution_path,
    source_version_file,
)
from distribution.installer.migrate_layout import (
    apply_layout_migration,
    iter_legacy_migration_destination_files,
    plan_layout_migration,
    remove_migrated_legacy_paths,
)
from distribution.installer.migrate_v1_v2 import MigrationError, ensure_installation_record_v2
from distribution.installer.migrate_v2_v3 import (
    MigrationError as MigrationErrorV2V3,
    ensure_installation_record_v3,
)
from distribution.installer.record import (
    INSTALLATION_RECORD_FILE,
    LEGACY_VERSION_FILE,
    is_installation_record,
    load_installation_record,
    managed_file_hashes,
    managed_files_union,
    read_installation_manifest,
)
from distribution.installer.repository_kind import framework_source_install_error
from distribution.installer.snapshot import create_snapshot, rollback_paths
from distribution.installer.source_files import (
    build_copy_plan,
    bootstrap_adapter_imports,
    detect_obsolete_managed,
)


def _yaml_module():
    import yaml

    return yaml


def _load_profile_yaml(target: Path, *, validator: Path | None = None) -> dict:
    profile_path = target / ".ai-team" / "project-profile.yaml"
    text = profile_path.read_text(encoding="utf-8")
    try:
        return _yaml_module().safe_load(text) or {}
    except ModuleNotFoundError:
        candidate = validator or validation_python(target)
        if candidate is None:
            raise
        result = subprocess.run(
            [
                str(candidate),
                "-c",
                "import sys, yaml, json; json.dump(yaml.safe_load(sys.stdin.read()) or {}, sys.stdout)",
            ],
            input=text,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise ModuleNotFoundError("yaml") from None
        return json.loads(result.stdout)


@dataclass
class UpdatePlan:
    git_state: str
    dirty_paths: list[str]
    installed_version: str | None
    new_version: str
    entries: list
    migration_changes: list
    constitution_change: tuple[str, str] | None
    obsolete: list[str]
    managed_files: list[str]


def current_version(source_root: Path) -> str:
    payload = json.loads(source_version_file(source_root).read_text(encoding="utf-8"))
    return payload["version"]


def source_constitution_version(source_root: Path) -> str:
    text = source_constitution_path(source_root).read_text(encoding="utf-8")
    match = re.search(r'(?m)^\s{2}version:\s*["\']?([^"\'\s]+)', text)
    if not match:
        raise ValueError("Source Constitution version is missing or malformed")
    return match.group(1)


def target_constitution_state(target: Path) -> tuple[str | None, str | None]:
    path = target / ".ai-team" / "state" / "project-state.yaml"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    version_match = re.search(r'(?m)^constitution_version:\s*["\']?([^"\'\s]+)', text)
    phase_match = re.search(r'(?m)^phase:\s*["\']?([^"\'\s]+)', text)
    return (
        version_match.group(1) if version_match else None,
        phase_match.group(1) if phase_match else None,
    )


def read_installed_manifest(target: Path) -> dict:
    record_path = target / INSTALLATION_RECORD_FILE
    if record_path.is_file():
        payload = read_installation_manifest(target)
        if is_installation_record(payload):
            validate_installation_record(payload)
            return {
                "schema_version": payload.get("schema_version"),
                "version": str(payload["core"]["version"]),
                "managed_files": sorted(managed_files_union(payload)),
                "installation_record": payload,
            }
    path = target / LEGACY_VERSION_FILE
    if not path.exists():
        return {"schema_version": 1, "version": None, "managed_files": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
        raise ValueError("Invalid installed framework version file: version must be a string")
    return payload


def target_git_status(target: Path) -> tuple[str, list[str]]:
    try:
        root_result = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unversioned", []
    if root_result.returncode != 0:
        return "unversioned", []
    git_root = Path(root_result.stdout.strip()).resolve()
    if git_root != target:
        return "unversioned", []
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if status.returncode != 0:
        return "error", [status.stderr.strip() or "git status failed"]
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    return ("dirty" if lines else "clean"), lines


def load_migration_module(source_root: Path):
    path = source_root / "scripts" / "ai-team" / "migrate.py"
    spec = importlib.util.spec_from_file_location("governed_ai_migrations", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validation_python(target: Path) -> Path | None:
    candidates = [
        target / ".venv" / "bin" / "python",
        target / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    req = target / ".ai-team" / "requirements.txt"
    if not req.is_file():
        req = target / "requirements.txt"
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        probe = subprocess.run(
            [str(candidate), "-c", "import yaml, jsonschema"],
            text=True,
            capture_output=True,
            timeout=15,
        )
        if probe.returncode == 0:
            return candidate
    return None


def write_forced_constitution_event(
    target: Path, old_version: str, new_version: str, phase: str
) -> Path:
    timestamp = datetime.now(timezone.utc)
    event_id = f"EVT-{timestamp:%Y%m%dT%H%M%SZ}-CONSTITUTION-FORCE-UPDATE"
    events_dir = target / ".ai-team" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / f"{event_id}.yaml"
    summary = (
        f"Constitution force-updated {old_version} -> {new_version} via "
        f"'tools/install.py --update --force-constitution-update' while project phase was "
        f"'{phase}', bypassing freeze_policy."
    )
    content = (
        f"id: {event_id}\n"
        "type: CONTRACT_CHANGE\n"
        "work_unit: null\n"
        f"created_at: '{timestamp.isoformat(timespec='seconds')}'\n"
        "created_by_role: human\n"
        f"summary: >-\n  {summary}\n"
        "details:\n"
        f"  old_constitution_version: \"{old_version}\"\n"
        f"  new_constitution_version: \"{new_version}\"\n"
        f"  phase_at_override: \"{phase}\"\n"
        "  note: >-\n"
        "    Work Units already gated (G1/G2/G3/G4) under the old Constitution version\n"
        "    were not retroactively re-validated against the new version. Review\n"
        "    open/in-flight Work Units for impact before their next gate.\n"
        "affected_nodes: []\n"
        "requires_human: true\n"
        "status: open\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def print_update_plan(target: Path, plan: UpdatePlan) -> None:
    print("Governed AI Team update plan")
    print("=" * 29)
    print(f"Target: {target}")
    print(f"Version: {plan.installed_version or 'legacy/unversioned'} -> {plan.new_version}")
    print(f"Git worktree: {plan.git_state}")
    for line in plan.dirty_paths:
        print(f"DIRTY   {line}")
    for entry in plan.entries:
        if entry.action != "unchanged":
            print(f"{entry.action.upper():7} {entry.relative.as_posix()}")
    for change in plan.migration_changes:
        print(f"MIGRATE {change.path.relative_to(target).as_posix()}")
    if plan.constitution_change:
        old_version, new_version = plan.constitution_change
        print(
            "MIGRATE .ai-team/state/project-state.yaml "
            f"constitution_version {old_version} -> {new_version}"
        )
    for path in plan.obsolete:
        print(f"OBSOLETE {path} (left untouched)")
    changed = sum(entry.action != "unchanged" for entry in plan.entries)
    print(
        f"Summary: {changed} framework file change(s), "
        f"{len(plan.migration_changes) + bool(plan.constitution_change)} "
        "project-data migration(s), "
        f"{len(plan.obsolete)} obsolete managed file(s)."
    )


def _can_compile_cursor(source_root: Path, target: Path | None = None) -> bool:
    try:
        bootstrap_adapter_imports(source_root, target)
        import jsonschema  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


def build_update_plan(source_root: Path, target: Path, *, compile_cursor: bool | None = None) -> UpdatePlan:
    installed = read_installed_manifest(target)
    new_version = current_version(source_root)
    git_state, dirty_paths = target_git_status(target)
    cursor_compile = (
        _can_compile_cursor(source_root, target) if compile_cursor is None else compile_cursor
    )
    entries, managed_files = build_copy_plan(
        source_root, target, compile_cursor=cursor_compile
    )
    old_managed = set(installed.get("managed_files") or [])
    obsolete = detect_obsolete_managed(old_managed, set(managed_files))
    migrations = load_migration_module(source_root)
    migration_changes = migrations.plan_acceptance_status(target)
    new_constitution_version = source_constitution_version(source_root)
    installed_constitution_version, _phase = target_constitution_state(target)
    constitution_change = None
    if (
        installed_constitution_version
        and installed_constitution_version != new_constitution_version
    ):
        constitution_change = (installed_constitution_version, new_constitution_version)
    return UpdatePlan(
        git_state=git_state,
        dirty_paths=dirty_paths,
        installed_version=installed.get("version"),
        new_version=new_version,
        entries=entries,
        migration_changes=migration_changes,
        constitution_change=constitution_change,
        obsolete=obsolete,
        managed_files=managed_files,
    )


def _project_id_from_target(target: Path, *, validator: Path | None = None) -> str:
    profile = _load_profile_yaml(target, validator=validator)
    return str(profile.get("project", {}).get("id", ""))


def _active_adapter_id(target: Path, *, validator: Path | None = None) -> str:
    profile = _load_profile_yaml(target, validator=validator)
    return str(profile.get("active_adapter_id", "cursor"))


def _needs_layout_migration(target: Path) -> bool:
    # Presence-based, not a version-string match: any pre-0.7.0 install —
    # 0.6.0, 0.5.0, or older — left src/governed_ai and/or adapters/cursor
    # at the target root, regardless of what its recorded version string
    # says. Reacting to the actual legacy layout, not to "== 0.6.0", means
    # this keeps working even for versions this exact check was never
    # updated for.
    return bool(plan_layout_migration(target).moved)


def run_update(source_root: Path, args: Namespace, target: Path) -> int:
    install_error = framework_source_install_error(source_root, target)
    if install_error:
        print(install_error)
        return 2

    if not (target / ".ai-team" / "project-profile.yaml").exists():
        print(
            f"--update expects an installed project at {target}; "
            ".ai-team/project-profile.yaml is missing."
        )
        return 2

    new_version = current_version(source_root)

    try:
        installed = read_installed_manifest(target)
        validate_update_path(installed.get("version"), new_version)
    except (ValueError, InstallationValidationError) as exc:
        print(exc)
        return 2

    installed_constitution_version, phase = target_constitution_state(target)
    new_constitution_version = source_constitution_version(source_root)
    constitution_change = None
    if (
        installed_constitution_version
        and installed_constitution_version != new_constitution_version
    ):
        constitution_change = (
            installed_constitution_version,
            new_constitution_version,
        )
        if phase not in {"not_compiled", "completed"} and not args.force_constitution_update:
            print(
                "Update aborted before writing files: Constitution "
                f"{installed_constitution_version} is frozen while project phase is "
                f"{phase!r}. Finish or explicitly close the current execution cycle "
                f"before activating Constitution {new_constitution_version}, or pass "
                "--force-constitution-update to override at your own risk."
            )
            return 2

    forced_constitution_override = bool(
        constitution_change
        and phase not in {"not_compiled", "completed"}
        and args.force_constitution_update
    )
    if forced_constitution_override:
        print(
            "WARNING: forcing Constitution "
            f"{constitution_change[0]} -> {constitution_change[1]} while project phase is "
            f"{phase!r}. This bypasses freeze_policy; Work Units already gated under "
            f"Constitution {constitution_change[0]} are NOT retroactively re-validated. "
            "A CONTRACT_CHANGE event will be recorded for human review."
        )

    plan = build_update_plan(source_root, target)

    existing_record = load_installation_record(target)
    if existing_record is None and not args.dry_run:
        legacy = target / LEGACY_VERSION_FILE
        if legacy.is_file():
            existing_record = read_installation_manifest(target)

    installed_hashes = managed_file_hashes(existing_record or {})
    drift = scan_local_drift_collisions(target, plan.entries, installed_hashes)
    if drift and not args.force:
        print(format_collision_report(drift))
        print("Update aborted: pass --force to overwrite locally modified managed files.")
        return 2

    print_update_plan(target, plan)
    if args.dry_run:
        print("DRY-RUN: no file was modified.")
        return 0

    try:
        migration = ensure_installation_record_v2(target, target_version=new_version)
    except MigrationError as exc:
        print(f"Installation record migration blocked: {exc}")
        return 2
    if migration is not None:
        print(
            "Migrated legacy framework-version.json to "
            f".ai-team/installation-record.json (backup: "
            f"{migration.backup_path.relative_to(target).as_posix()})."
        )
        existing_record = migration.record

    try:
        v3_migration = ensure_installation_record_v3(target)
    except MigrationErrorV2V3 as exc:
        print(f"Installation record migration blocked: {exc}")
        return 2
    if v3_migration is not None:
        print(
            "Migrated installation-record.json to schema v3 (content hashes; backup: "
            f"{v3_migration.backup_path.relative_to(target).as_posix()}). Local drift on "
            "managed files could not be checked for this transition update — it will be "
            "detected on the next one."
        )
        existing_record = v3_migration.record

    if plan.git_state != "clean" and not args.allow_dirty:
        print(
            "Update aborted before writing files: target must be a clean standalone Git "
            "worktree. Commit/stash existing work, or use --allow-dirty explicitly."
        )
        return 2

    validator = None if args.skip_validation else validation_python(target)
    if not args.skip_validation and validator is None:
        print(
            "Update aborted before writing files: no Python environment with PyYAML and "
            "jsonschema was found. The updater checked the target .venv and its own "
            "interpreter. Install requirements or use --skip-validation explicitly."
        )
        return 2

    changed_entries = [entry for entry in plan.entries if entry.action != "unchanged"]
    record_path = target / INSTALLATION_RECORD_FILE
    legacy_path = target / LEGACY_VERSION_FILE
    state_path = target / ".ai-team" / "state" / "project-state.yaml"
    touched = collect_changed_destinations(changed_entries)
    touched.extend(change.path for change in plan.migration_changes)
    if plan.constitution_change:
        touched.append(state_path)
    touched.extend([record_path, legacy_path])

    needs_layout_migration = _needs_layout_migration(target)
    pending_layout_moves: list[tuple[str, str]] = []
    if needs_layout_migration:
        # These paths do not exist yet (the migration hasn't run); include
        # them so a failure anywhere in this transaction unwinds the
        # freshly-copied new layout via the normal file-level rollback,
        # not just the legacy directories (which apply_layout_migration
        # itself never deletes until the transaction fully succeeds).
        touched.extend(iter_legacy_migration_destination_files(target))
        # Computed up front (read-only) so the except-block cleanup below
        # knows which destination directories to remove even if the
        # migration call itself raises before returning a result.
        pending_layout_moves = plan_layout_migration(target).moved

    project_id = _project_id_from_target(target, validator=validator)
    active_adapter = _active_adapter_id(target, validator=validator)

    layout_result = None
    with tempfile.TemporaryDirectory(prefix="governed-ai-update-") as temp_dir:
        backup_root = Path(temp_dir)
        snapshot = create_snapshot(target, touched, backup_root)
        migration_backup = None
        try:
            if needs_layout_migration:
                layout_result = apply_layout_migration(
                    target,
                    version_from=plan.installed_version or "0.6.0",
                    version_to=plan.new_version,
                )
                if layout_result.moved:
                    print(f"Layout migration: moved {len(layout_result.moved)} path(s).")
                for event in layout_result.forensic_events:
                    print(
                        f"Recorded forensic review event: "
                        f"{event.relative_to(target).as_posix()}"
                    )

            apply_copy_entries(
                source_root,
                target,
                changed_entries,
                project_id=project_id,
            )

            migrations = load_migration_module(source_root)
            migration_backup = migrations.apply_acceptance_changes(target, plan.migration_changes)
            if plan.constitution_change:
                old_version, new_constitution_version = plan.constitution_change
                state_text = state_path.read_text(encoding="utf-8")
                state_text, replacements = re.subn(
                    r'(?m)^constitution_version:\s*["\']?[^"\'\s]+["\']?\s*$',
                    f'constitution_version: "{new_constitution_version}"',
                    state_text,
                    count=1,
                )
                if replacements != 1:
                    raise RuntimeError(
                        "Could not migrate Project State constitution_version "
                        f"from {old_version} to {new_constitution_version}"
                    )
                state_path.write_text(state_text, encoding="utf-8")

            finalize_installation_manifests(
                target,
                project_id=project_id,
                version=plan.new_version,
                managed_files=plan.managed_files,
                active_adapter_id=active_adapter,
                existing_record=existing_record,
                schema_version=3,
            )

            if validator is not None:
                validation = subprocess.run(
                    [str(validator), "scripts/ai-team/validate.py"],
                    cwd=target,
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                if validation.returncode != 0:
                    raise RuntimeError(
                        "Post-update validation failed:\n"
                        + validation.stdout
                        + validation.stderr
                    )
        except Exception as exc:
            rollback_paths(touched, snapshot.existing_paths, target, backup_root)
            for _src_prefix, dest_prefix in pending_layout_moves:
                dest_dir = target / dest_prefix
                if dest_dir.is_dir():
                    shutil.rmtree(dest_dir, ignore_errors=True)
            print(str(exc))
            print("Update rolled back; target files and installation manifests were restored.")
            return 1

    if layout_result is not None and layout_result.moved:
        remove_migrated_legacy_paths(target, layout_result.moved)

    print(f"Update complete: framework {plan.new_version} installed.")
    if plan.migration_changes:
        print(f"Migrated {len(plan.migration_changes)} project-data file(s).")
        if migration_backup is not None:
            print(f"Migration backup: {migration_backup.relative_to(target)}")
    if plan.constitution_change:
        print(
            "Activated Constitution "
            f"{plan.constitution_change[1]} for the next safe execution cycle."
        )
    if forced_constitution_override:
        event_path = write_forced_constitution_event(
            target, plan.constitution_change[0], plan.constitution_change[1], phase
        )
        print(
            f"Recorded {event_path.relative_to(target).as_posix()} "
            "(CONTRACT_CHANGE, requires_human: true) — review it before the next G4."
        )
    if plan.obsolete:
        print("Obsolete managed files were reported but not deleted.")
    if validator is not None:
        print("Post-update validation: PASS")
    else:
        print("WARNING: post-update validation was explicitly skipped.")
    print("Before Cursor CLI, run: python scripts/ai-team/preflight.py.")
    return 0


def _write_project_seeds(source_root: Path, target: Path, args: Namespace) -> None:
    for src_rel, dest_rel in FRESH_PROJECT_SEED_SOURCES:
        src = source_root / src_rel
        if not src.is_file():
            continue
        dest = target / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    for pattern in PROJECT_OWNED_PATTERNS:
        if pattern.endswith("/*"):
            (target / pattern[:-2]).mkdir(parents=True, exist_ok=True)

    profile_path = target / ".ai-team" / "project-profile.yaml"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Missing seed file: {profile_path}")
    profile_text = profile_path.read_text(encoding="utf-8")
    substitutions = [
        ("  id: framework-template", f"  id: {args.project_id}"),
        ("  name: Governed AI Development Team Framework", f"  name: {args.project_name}"),
        (
            "  repository_kind: framework_template",
            "  repository_kind: existing_or_greenfield_project",
        ),
        (
            "  repository_kind: framework_source",
            "  repository_kind: existing_or_greenfield_project",
        ),
        ("  template: true", "  template: false"),
        (
            '  note: "The installer rewrites project.id, project.name and template=false. '
            "Fill repository-specific commands, paths and human authorities before "
            'production use."',
            '  note: "Complete commands, paths and human authorities before production use."',
        ),
    ]
    if all(profile_text.count(old) == 1 for old, _new in substitutions):
        for old, new in substitutions:
            profile_text = profile_text.replace(old, new, 1)
        profile_path.write_text(profile_text, encoding="utf-8")
    else:
        profile = _yaml_module().safe_load(profile_text)
        profile["project"]["id"] = args.project_id
        profile["project"]["name"] = args.project_name
        profile["project"]["repository_kind"] = "existing_or_greenfield_project"
        profile["setup_status"]["template"] = False
        profile["setup_status"]["note"] = (
            "Complete commands, paths and human authorities before production use."
        )
        profile_path.write_text(
            _yaml_module().safe_dump(profile, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    profile = _yaml_module().safe_load(profile_path.read_text(encoding="utf-8"))
    profile["active_adapter_id"] = "cursor"
    profile_path.write_text(
        _yaml_module().safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    state_path = target / ".ai-team" / "state" / "project-state.yaml"
    constitution_version = source_constitution_version(source_root)
    state = {
        "project_id": args.project_id,
        "constitution_version": constitution_version,
        "phase": "not_compiled",
        "gates": {gate: {"status": "not_required"} for gate in ("G0", "G1", "G2", "G3", "G4")},
        "work_units": {},
        "dependency_edges": [],
        "active_workers": [],
        "open_decisions": [],
        "open_blockers": [],
        "open_defects": [],
        "open_findings": [],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _yaml_module().safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def install_fresh(source_root: Path, args: Namespace, target: Path) -> int:
    install_error = framework_source_install_error(source_root, target)
    if install_error:
        print(install_error)
        return 2

    try:
        import yaml as _yaml
    except ModuleNotFoundError:
        print("Missing dependency: PyYAML. Install it first, then re-run this command:")
        print("  pip install -r requirements.txt")
        return 1

    _ = _yaml
    target.mkdir(parents=True, exist_ok=True)

    entries, managed_files = build_copy_plan(source_root, target, project_id=args.project_id)
    seed_destinations = [target / dest_rel for _src_rel, dest_rel in FRESH_PROJECT_SEED_SOURCES]
    copy_destinations = collect_changed_destinations(entries)
    collision_destinations = seed_destinations + copy_destinations

    collisions = scan_fresh_install_collisions(target, collision_destinations)
    if collisions and not args.force:
        print(format_collision_report(collisions))
        print("Install aborted: pass --force to overwrite conflicting paths.")
        return 2

    record_path = target / INSTALLATION_RECORD_FILE
    legacy_path = target / LEGACY_VERSION_FILE
    touched = list(collision_destinations) + [record_path, legacy_path]
    version = current_version(source_root)

    with tempfile.TemporaryDirectory(prefix="governed-ai-install-") as temp_dir:
        backup_root = Path(temp_dir)
        snapshot = create_snapshot(target, touched, backup_root)
        try:
            _write_project_seeds(source_root, target, args)
            apply_copy_entries(
                source_root,
                target,
                entries,
                project_id=args.project_id,
            )
            finalize_installation_manifests(
                target,
                project_id=args.project_id,
                version=version,
                managed_files=managed_files,
                active_adapter_id="cursor",
                schema_version=3,
            )
        except Exception as exc:
            rollback_paths(touched, snapshot.existing_paths, target, backup_root)
            print(str(exc))
            print("Install rolled back; target files and installation manifests were restored.")
            return 1

    print(f"Installed governed AI team framework {version} into {target}")
    print("Next:")
    print("  1. Fill .ai-team/project-profile.yaml (or ask Cursor: /propose-profile)")
    print("  2. Add and register authoritative product documents")
    print("  3. Run: python scripts/ai-team/validate.py")
    print("  4. Before Cursor CLI, run: python scripts/ai-team/preflight.py")
    print("  5. In Cursor UI or interactive CLI, invoke /compile-project")
    return 0
