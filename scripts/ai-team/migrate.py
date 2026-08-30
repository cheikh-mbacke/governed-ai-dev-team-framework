#!/usr/bin/env python3
"""Plan or apply idempotent project-data migrations.

The module intentionally uses only the Python standard library so an upgrade
can inspect legacy data before the target project's optional dependencies are
available.
"""

from __future__ import annotations

import argparse
import codecs
from dataclasses import dataclass
from pathlib import Path
import re
import shutil


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_MIGRATION_ID = "acceptance-status-passed"
HUMAN_RESULT_RE = re.compile(r"^(?P<indent> *)human_result\s*:\s*(?:#.*)?$")
STATUS_RE = re.compile(
    r"^(?P<prefix>\s*status\s*:\s*)(?P<quote>[\"']?)accepted(?P=quote)"
    r"(?P<suffix>\s*(?:#.*)?)$"
)


@dataclass(frozen=True)
class MigrationChange:
    path: Path
    original_bytes: bytes
    migrated_bytes: bytes
    replacements: int


def _line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


def _migrate_acceptance_text(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    output = []
    human_result_indent = None
    replacements = 0

    for line in lines:
        body, ending = _line_ending(line)
        stripped = body.strip()
        indentation = len(body) - len(body.lstrip(" "))

        match_human = HUMAN_RESULT_RE.match(body)
        if match_human:
            human_result_indent = len(match_human.group("indent"))
        elif human_result_indent is not None and stripped and not stripped.startswith("#"):
            if indentation <= human_result_indent:
                human_result_indent = None
            else:
                match_status = STATUS_RE.match(body)
                if match_status:
                    body = (
                        match_status.group("prefix")
                        + match_status.group("quote")
                        + "passed"
                        + match_status.group("quote")
                        + match_status.group("suffix")
                    )
                    replacements += 1

        output.append(body + ending)

    return "".join(output), replacements


def plan_acceptance_status(target: Path) -> list[MigrationChange]:
    acceptance_dir = target / ".ai-team" / "acceptance"
    changes = []
    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(acceptance_dir.glob(pattern)):
            original = path.read_bytes()
            has_bom = original.startswith(codecs.BOM_UTF8)
            text = original.decode("utf-8-sig")
            migrated_text, replacements = _migrate_acceptance_text(text)
            if replacements:
                migrated = (codecs.BOM_UTF8 if has_bom else b"") + migrated_text.encode(
                    "utf-8"
                )
                changes.append(
                    MigrationChange(
                        path=path,
                        original_bytes=original,
                        migrated_bytes=migrated,
                        replacements=replacements,
                    )
                )
    return changes


def apply_acceptance_changes(target: Path, changes: list[MigrationChange]) -> Path | None:
    if not changes:
        return None
    backup_root = target / ".ai-team" / "migration-backups" / ACCEPTANCE_MIGRATION_ID
    for change in changes:
        relative = change.path.relative_to(target)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(change.path, backup)
        change.path.write_bytes(change.migrated_bytes)
    return backup_root


def _mutable_v2_module_path(root: Path) -> Path:
    candidates = [
        root
        / ".ai-team"
        / "runtime"
        / "governed_ai"
        / "core"
        / "persistence"
        / "migrations"
        / "mutable_v2.py",
        root / "src" / "governed_ai" / "core" / "persistence" / "migrations" / "mutable_v2.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("unable to locate mutable_v2 migration module")


def _load_mutable_v2_module():
    import importlib.util
    import sys

    module_path = _mutable_v2_module_path(DEFAULT_ROOT)
    module_name = "governed_ai_mutable_v2_migration"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load migration module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _plan_mutable_v2(target: Path):
    return _load_mutable_v2_module().plan_mutable_v2(target)


def _apply_mutable_v2(target: Path, plan):
    return _load_mutable_v2_module().apply_mutable_v2(target, plan)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate governed AI team project data")
    parser.add_argument("--target", default=str(DEFAULT_ROOT))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply planned migrations; the default is a read-only dry run",
    )
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()
    acceptance_changes = plan_acceptance_status(target)
    mutable_plan = None
    mutable_error = None
    try:
        mutable_plan = _plan_mutable_v2(target)
    except Exception as exc:
        mutable_error = exc

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Governed AI Team migrations ({mode})")
    print("=" * 36)

    if mutable_error is not None:
        print(f"ERROR mutable-schema-v2: {mutable_error}")
        return 1

    if not acceptance_changes and not mutable_plan.changes:
        print("No project-data migration required.")
        return 0

    for change in acceptance_changes:
        relative = change.path.relative_to(target)
        print(f"MIGRATE {relative} ({change.replacements} replacement(s)) [acceptance-status-passed]")
    for change in mutable_plan.changes:
        relative = change.path.relative_to(target)
        print(f"MIGRATE {relative} [mutable-schema-v2]")
    for skipped in mutable_plan.skipped:
        relative = skipped.relative_to(target)
        print(f"SKIP {relative} [legacy gate decision]")

    if args.apply:
        if acceptance_changes:
            backup_root = apply_acceptance_changes(target, acceptance_changes)
            print(f"Backup: {backup_root.relative_to(target)}")
            print(f"Applied {len(acceptance_changes)} acceptance migration(s).")
        if mutable_plan.changes:
            backup_root = _apply_mutable_v2(target, mutable_plan)
            print(f"Backup: {backup_root.relative_to(target)}")
            print(f"Applied {len(mutable_plan.changes)} mutable v2 migration(s).")
    else:
        print("No file was modified. Re-run with --apply after reviewing this plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
