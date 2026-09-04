#!/usr/bin/env python3
"""Install or transactionally update the Governed AI Dev Team framework."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
SRC_ROOT = SOURCE_ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.assessment import ASSESSMENT_SKIP_ENV, assessment_gate_error
from distribution.installer.operations import install_fresh, run_update


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install Governed AI Dev Team framework into an existing repository"
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--project-name")
    parser.add_argument(
        "--assessment-report",
        help=(
            "Fresh install: path to JSON report from tools/assess.py with verdict "
            "go or go_with_backlog (Document 19)."
        ),
    )
    parser.add_argument(
        "--skip-assessment-gate",
        action="store_true",
        help=(
            "Fresh install: explicitly bypass the assessment gate (prints a warning). "
            f"Automation may set {ASSESSMENT_SKIP_ENV}=1 instead."
        ),
    )
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
    if args.update and (args.assessment_report or args.skip_assessment_gate):
        parser.error("--assessment-report and --skip-assessment-gate apply only to fresh install")
    return args


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()
    if args.update:
        return run_update(SOURCE_ROOT, args, target)
    gate_error = assessment_gate_error(
        assessment_report=args.assessment_report,
        skip_assessment_gate=bool(args.skip_assessment_gate),
    )
    if gate_error:
        print(gate_error)
        return 2
    skipped = bool(args.skip_assessment_gate) or (
        not args.assessment_report and os.environ.get(ASSESSMENT_SKIP_ENV) == "1"
    )
    if skipped:
        print(
            "WARNING: assessment gate skipped — exclusive governance still required; "
            "hybrid adoption is not supported."
        )
    elif args.assessment_report:
        print(f"Assessment gate: accepted report {args.assessment_report}")
    return install_fresh(SOURCE_ROOT, args, target)


if __name__ == "__main__":
    raise SystemExit(main())
