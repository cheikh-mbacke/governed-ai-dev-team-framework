#!/usr/bin/env python3
"""Install or transactionally update the Governed AI Dev Team framework."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
SRC_ROOT = SOURCE_ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.operations import install_fresh, run_update


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install Governed AI Dev Team framework into an existing repository"
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--project-name")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Fresh install: proceed despite path collisions with existing project files. "
            "With --update: proceed despite locally modified managed files (local drift)."
        ),
    )
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
    if not args.update and (not args.project_id or not args.project_name):
        parser.error("--project-id and --project-name are required for a fresh install")
    return args


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()
    if args.update:
        return run_update(SOURCE_ROOT, args, target)
    return install_fresh(SOURCE_ROOT, args, target)


if __name__ == "__main__":
    raise SystemExit(main())
