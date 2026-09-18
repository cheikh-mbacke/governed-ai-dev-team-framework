#!/usr/bin/env python3
"""Read-only adoption assessment for a target repository (Documents 19–20)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
SRC_ROOT = SOURCE_ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.assessment import (
    exit_code_for_verdict,
    format_human_report,
    load_resolutions_file,
    run_assessment,
    run_ensemble_assessment,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Assess adoption conflicts for a target repository without modifying it. "
            "Not preflight, diagnose, or gate G0. Hybrid governance is not supported."
        )
    )
    parser.add_argument(
        "--target",
        help="Path to a single candidate project root (standalone assessment)",
    )
    parser.add_argument(
        "--instance",
        help="Instance root for an ensemble assessment (Document 25)",
    )
    parser.add_argument(
        "--member",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="Declared member to include (repeatable). Requires --instance.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable assessment report as JSON on stdout",
    )
    parser.add_argument(
        "--report-file",
        help=(
            "Optional path to write the JSON report. Does not write under the target "
            "unless this path is explicitly inside it."
        ),
    )
    parser.add_argument(
        "--resolutions",
        help=(
            "Optional JSON file applying resolution_status per finding id "
            "(eliminate|remap|waive+waiver_authorization_id|defer_blocks_adoption)"
        ),
    )
    args = parser.parse_args(argv)
    if args.member and not args.instance:
        parser.error("--member requires --instance")
    if args.instance and args.target:
        parser.error("use --instance or --target, not both")
    if not args.instance and not args.target:
        parser.error("--target or --instance is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # Avoid Windows cp1252 failures on JSON/human reports.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    resolutions = None
    if args.resolutions:
        try:
            resolutions = load_resolutions_file(Path(args.resolutions))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Invalid --resolutions file: {exc}", file=sys.stderr)
            return 1
    try:
        if args.instance:
            members: list[tuple[str, Path]] = []
            for item in args.member:
                if "=" not in item:
                    print("each --member must be ID=PATH", file=sys.stderr)
                    return 1
                member_id, raw_path = item.split("=", 1)
                members.append((member_id, Path(raw_path)))
            report = run_ensemble_assessment(
                Path(args.instance).expanduser().resolve(),
                members,
                source_root=SOURCE_ROOT,
                resolutions=resolutions,
            )
        else:
            report = run_assessment(
                Path(args.target).expanduser().resolve(),
                source_root=SOURCE_ROOT,
                resolutions=resolutions,
            )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report_json = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report_file:
        report_path = Path(args.report_file).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_json, encoding="utf-8")

    if args.json:
        sys.stdout.write(report_json)
    else:
        sys.stdout.write(format_human_report(report))
        if args.report_file:
            print(f"JSON report written to: {args.report_file}")

    return exit_code_for_verdict(str(report["verdict"]))


if __name__ == "__main__":
    raise SystemExit(main())
