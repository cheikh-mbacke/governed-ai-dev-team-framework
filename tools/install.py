#!/usr/bin/env python3
"""Install or transactionally update the Governed AI Dev Team framework."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SOURCE_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = Path(".ai-team/framework-version.json")
COPY_ITEMS = [
    ".cursor",
    ".ai-team",
    "scripts",
    "docs/product",
    "AGENTS.md",
    "requirements.txt",
]
PROJECT_OWNED_PATTERNS = [
    ".ai-team/project-profile.yaml",
    ".ai-team/sources/source-registry.yaml",
    ".ai-team/work-units/*",
    ".ai-team/state/*",
    ".ai-team/decisions/*",
    ".ai-team/events/*",
    ".ai-team/evidence/*",
    ".ai-team/findings/*",
    ".ai-team/audits/*",
    ".ai-team/releases/*",
    ".ai-team/acceptance/*",
    ".ai-team/context-packages/*",
    ".ai-team/logs/*",
    ".ai-team/metrics/*",
    ".ai-team/observations/*",
    ".ai-team/retrospectives/*",
    ".ai-team/migration-backups/*",
    ".ai-team/project-profile.yaml.bak",
]
SUPPORTED_UPDATE_FROM = {None, "0.1.0", "0.2.0", "0.3.0", "0.4.0"}


def _bootstrap_adapter_imports() -> None:
    root = str(SOURCE_ROOT)
    src = str(SOURCE_ROOT / "src")
    for entry in (root, src):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _compile_profile_for_target(target: Path, project_id: str | None = None) -> dict:
    _bootstrap_adapter_imports()
    from adapters.cursor.compiler.install_support import (
        load_project_profile_yaml,
        minimal_project_profile,
    )

    profile_path = target / ".ai-team" / "project-profile.yaml"
    if profile_path.is_file():
        return load_project_profile_yaml(profile_path)
    if project_id:
        return minimal_project_profile(project_id=project_id)
    return minimal_project_profile()


def materialize_cursor_dir(target: Path, project_id: str | None = None) -> None:
    """Install compiled ``.cursor/`` artefacts (default since WU-P4-SHADOW-COMPILE)."""
    _bootstrap_adapter_imports()
    from adapters.cursor.compiler.install_support import compile_cursor_tree

    profile = _compile_profile_for_target(target, project_id=project_id)
    compile_cursor_tree(SOURCE_ROOT, target / ".cursor", profile)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install Governed AI Dev Team framework into an existing repository"
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--project-name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "Transactionally refresh framework-owned files, migrate compatible legacy "
            "project data, and preserve project-owned state"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --update, show files and migrations without changing the target",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="with --update, explicitly allow a dirty or unversioned target (not recommended)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="with --update, skip post-update validate.py (not recommended)",
    )
    parser.add_argument(
        "--force-constitution-update",
        action="store_true",
        help=(
            "with --update, activate a new Constitution version even while the project "
            "phase is mid-cycle, bypassing the freeze_policy. Records a CONTRACT_CHANGE "
            "event for human review. Use only when you understand that Work Units already "
            "gated under the old Constitution are not retroactively re-validated."
        ),
    )
    args = parser.parse_args()
    update_only_flags = (
        args.dry_run
        or args.allow_dirty
        or args.skip_validation
        or args.force_constitution_update
    )
    if update_only_flags and not args.update:
        parser.error(
            "--dry-run, --allow-dirty, --skip-validation and --force-constitution-update "
            "require --update"
        )
    if args.update and args.force:
        parser.error("--update and --force are mutually exclusive")
    if not args.update and (not args.project_id or not args.project_name):
        parser.error("--project-id and --project-name are required for a fresh install")
    return args


def is_project_owned(rel_posix: str) -> bool:
    if rel_posix == ".ai-team/migration-backups/.gitignore":
        return False
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in PROJECT_OWNED_PATTERNS)


def is_docs_product_readme(rel_posix: str) -> bool:
    return rel_posix == "docs/product/README.md" or (
        rel_posix.startswith("docs/product/")
        and rel_posix.endswith("/README.md")
        and rel_posix.count("/") == 3
    )


def iter_managed_source_files(target: Path | None = None, project_id: str | None = None):
    profile = _compile_profile_for_target(target, project_id=project_id) if target else None
    for item in COPY_ITEMS:
        if item == ".cursor":
            _bootstrap_adapter_imports()
            from adapters.cursor.compiler.install_support import iter_compiled_cursor_files

            for relative, path in iter_compiled_cursor_files(SOURCE_ROOT, profile):
                rel_posix = relative.as_posix()
                if is_project_owned(rel_posix):
                    continue
                yield relative, path
            continue
        src = SOURCE_ROOT / item
        if not src.exists():
            continue
        paths = src.rglob("*") if src.is_dir() else [src]
        for path in paths:
            if path.is_dir():
                continue
            relative = path.relative_to(SOURCE_ROOT)
            rel_posix = relative.as_posix()
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if relative == VERSION_FILE:
                continue
            if item == "docs/product" and not is_docs_product_readme(rel_posix):
                continue
            if is_project_owned(rel_posix):
                continue
            yield relative, path


def current_version() -> str:
    payload = json.loads((SOURCE_ROOT / VERSION_FILE).read_text(encoding="utf-8"))
    return payload["version"]


def source_constitution_version() -> str:
    text = (SOURCE_ROOT / ".ai-team" / "constitution" / "constitution.yaml").read_text(
        encoding="utf-8"
    )
    match = re.search(r'(?m)^\s{2}version:\s*["\']?([^"\'\s]+)', text)
    if not match:
        raise ValueError("Source Constitution version is missing or malformed")
    return match.group(1)


def target_constitution_state(target: Path) -> tuple[str | None, str | None]:
    path = target / ".ai-team" / "state" / "project-state.yaml"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    version_match = re.search(
        r'(?m)^constitution_version:\s*["\']?([^"\'\s]+)', text
    )
    phase_match = re.search(r'(?m)^phase:\s*["\']?([^"\'\s]+)', text)
    return (
        version_match.group(1) if version_match else None,
        phase_match.group(1) if phase_match else None,
    )


def read_installed_manifest(target: Path) -> dict:
    _bootstrap_adapter_imports()
    from distribution.installer.record import (
        is_v2_record,
        managed_files_union,
        read_installation_manifest,
    )

    path = target / VERSION_FILE
    record_path = target / ".ai-team" / "installation-record.json"
    if record_path.is_file():
        payload = read_installation_manifest(target)
        if is_v2_record(payload):
            return {
                "schema_version": 2,
                "version": str(payload["core"]["version"]),
                "managed_files": sorted(managed_files_union(payload)),
            }
    if not path.exists():
        return {"schema_version": 1, "version": None, "managed_files": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid installed framework version file: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
        raise ValueError("Invalid installed framework version file: version must be a string")
    return payload


def manifest_bytes(version: str, managed_files: list[str]) -> bytes:
    payload = {
        "schema_version": 1,
        "version": version,
        "managed_files": sorted(managed_files),
    }
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


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


def load_migration_module():
    path = SOURCE_ROOT / "scripts" / "ai-team" / "migrate.py"
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


def copy_plan(target: Path):
    entries = []
    managed = []
    for relative, source in iter_managed_source_files(target):
        rel_posix = relative.as_posix()
        managed.append(rel_posix)
        destination = target / relative
        if not destination.exists():
            action = "add"
        elif destination.read_bytes() != source.read_bytes():
            action = "update"
        else:
            action = "unchanged"
        entries.append((action, relative, source, destination))
    managed.append(VERSION_FILE.as_posix())
    return entries, sorted(managed)


def snapshot(paths: list[Path], target: Path, backup_root: Path):
    existing = set()
    for path in paths:
        relative = path.relative_to(target)
        if path.exists():
            existing.add(relative.as_posix())
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
    return existing


def rollback(paths: list[Path], existing: set[str], target: Path, backup_root: Path):
    for path in sorted(set(paths), key=lambda item: len(item.parts), reverse=True):
        relative = path.relative_to(target)
        rel_posix = relative.as_posix()
        if rel_posix in existing:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_root / relative, path)
        elif path.exists() and path.is_file():
            path.unlink()


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
        f"'tools/install.py --update --force-constitution-update' while project phase "
        f"was '{phase}', bypassing freeze_policy."
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


def print_update_plan(
    target: Path,
    git_state: str,
    dirty_paths: list[str],
    installed_version: str | None,
    new_version: str,
    entries,
    migration_changes,
    constitution_change,
    obsolete: list[str],
):
    print("Governed AI Team update plan")
    print("=" * 29)
    print(f"Target: {target}")
    print(f"Version: {installed_version or 'legacy/unversioned'} -> {new_version}")
    print(f"Git worktree: {git_state}")
    for line in dirty_paths:
        print(f"DIRTY   {line}")
    for action, relative, _source, _destination in entries:
        if action != "unchanged":
            print(f"{action.upper():7} {relative.as_posix()}")
    for change in migration_changes:
        print(f"MIGRATE {change.path.relative_to(target).as_posix()}")
    if constitution_change:
        old_version, new_version = constitution_change
        print(
            "MIGRATE .ai-team/state/project-state.yaml "
            f"constitution_version {old_version} -> {new_version}"
        )
    for path in obsolete:
        print(f"OBSOLETE {path} (left untouched)")
    changed = sum(action != "unchanged" for action, *_rest in entries)
    print(
        f"Summary: {changed} framework file change(s), "
        f"{len(migration_changes) + bool(constitution_change)} "
        "project-data migration(s), "
        f"{len(obsolete)} obsolete managed file(s)."
    )


def run_update(args, target: Path) -> int:
    if not (target / ".ai-team" / "project-profile.yaml").exists():
        print(
            f"--update expects an installed project at {target}; "
            ".ai-team/project-profile.yaml is missing."
        )
        return 2

    _bootstrap_adapter_imports()
    from distribution.installer import MigrationError, ensure_installation_record_v2

    new_version = current_version()
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

    try:
        installed = read_installed_manifest(target)
    except ValueError as exc:
        print(exc)
        return 2
    installed_version = installed.get("version")
    if installed_version not in SUPPORTED_UPDATE_FROM:
        print(
            f"No safe migration path from framework version {installed_version!r} "
            f"to {new_version}. Update aborted before writing files."
        )
        return 2

    new_constitution_version = source_constitution_version()
    installed_constitution_version, phase = target_constitution_state(target)
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

    git_state, dirty_paths = target_git_status(target)
    entries, managed_files = copy_plan(target)
    old_managed = set(installed.get("managed_files") or [])
    obsolete = sorted(
        path for path in old_managed - set(managed_files) if (target / path).exists()
    )
    migrations = load_migration_module()
    migration_changes = migrations.plan_acceptance_status(target)
    print_update_plan(
        target,
        git_state,
        dirty_paths,
        installed_version,
        new_version,
        entries,
        migration_changes,
        constitution_change,
        obsolete,
    )
    if args.dry_run:
        print("DRY-RUN: no file was modified.")
        return 0
    if git_state != "clean" and not args.allow_dirty:
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

    changed_entries = [entry for entry in entries if entry[0] != "unchanged"]
    marker = target / VERSION_FILE
    marker_content = manifest_bytes(new_version, managed_files)
    marker_changes = not marker.exists() or marker.read_bytes() != marker_content
    touched = [entry[3] for entry in changed_entries]
    touched.extend(change.path for change in migration_changes)
    state_path = target / ".ai-team" / "state" / "project-state.yaml"
    if constitution_change:
        touched.append(state_path)
    if marker_changes:
        touched.append(marker)

    with tempfile.TemporaryDirectory(prefix="governed-ai-update-") as temp_dir:
        backup_root = Path(temp_dir)
        existing = snapshot(touched, target, backup_root)
        try:
            for _action, _relative, source, destination in changed_entries:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            migration_backup = migrations.apply_changes(target, migration_changes)
            if constitution_change:
                old_version, new_constitution_version = constitution_change
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
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(marker_content)

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
            rollback(touched, existing, target, backup_root)
            print(str(exc))
            print("Update rolled back; target files were restored.")
            return 1

    print(f"Update complete: framework {new_version} installed.")
    if migration_changes:
        print(f"Migrated {len(migration_changes)} project-data file(s).")
        if migration_backup is not None:
            print(f"Migration backup: {migration_backup.relative_to(target)}")
    if constitution_change:
        print(
            "Activated Constitution "
            f"{constitution_change[1]} for the next safe execution cycle."
        )
    if forced_constitution_override:
        event_path = write_forced_constitution_event(
            target, constitution_change[0], constitution_change[1], phase
        )
        print(
            f"Recorded {event_path.relative_to(target).as_posix()} "
            "(CONTRACT_CHANGE, requires_human: true) — review it before the next G4."
        )
    if obsolete:
        print("Obsolete managed files were reported but not deleted.")
    if validator is not None:
        print("Post-update validation: PASS")
    else:
        print("WARNING: post-update validation was explicitly skipped.")
    print("Before Cursor CLI, run python scripts/ai-team/preflight.py.")
    return 0


def install_fresh(args, target: Path) -> int:
    try:
        import yaml
    except ModuleNotFoundError:
        print("Missing dependency: PyYAML. Install it first, then re-run this command:")
        print("  pip install -r requirements.txt")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    for item in COPY_ITEMS:
        if item == ".cursor":
            continue
        src = SOURCE_ROOT / item
        dst = target / item
        if not src.exists():
            continue
        if src.is_dir():
            if dst.exists() and not args.force:
                for path in src.rglob("*"):
                    relative = path.relative_to(src)
                    output = dst / relative
                    if "__pycache__" in relative.parts or path.suffix == ".pyc":
                        continue
                    if path.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                    elif not output.exists():
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, output)
            else:
                shutil.copytree(
                    src,
                    dst,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        elif not dst.exists() or args.force:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile_text = profile_path.read_text(encoding="utf-8")
    substitutions = [
        ("  id: framework-template", f"  id: {args.project_id}"),
        ("  name: Governed AI Development Team Framework", f"  name: {args.project_name}"),
        (
            "  repository_kind: framework_template",
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
        profile = yaml.safe_load(profile_text)
        profile["project"]["id"] = args.project_id
        profile["project"]["name"] = args.project_name
        profile["project"]["repository_kind"] = "existing_or_greenfield_project"
        profile["setup_status"]["template"] = False
        profile["setup_status"]["note"] = (
            "Complete commands, paths and human authorities before production use."
        )
        profile_path.write_text(
            yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    state_path = target / ".ai-team" / "state" / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["project_id"] = args.project_id
    state_path.write_text(
        yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    materialize_cursor_dir(target, project_id=args.project_id)
    managed_files = [
        relative.as_posix() for relative, _source in iter_managed_source_files(target)
    ]
    (target / VERSION_FILE).write_bytes(manifest_bytes(current_version(), managed_files))

    print(f"Installed governed AI team framework {current_version()} into {target}")
    print("Next:")
    print("  1. Fill .ai-team/project-profile.yaml (or ask Cursor: /propose-profile)")
    print("  2. Add and register authoritative product documents")
    print("  3. Run: python scripts/ai-team/validate.py")
    print("  4. Before Cursor CLI, run: python scripts/ai-team/preflight.py")
    print("  5. In Cursor UI or interactive CLI, invoke /compile-project")
    return 0


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()
    return run_update(args, target) if args.update else install_fresh(args, target)


if __name__ == "__main__":
    raise SystemExit(main())
