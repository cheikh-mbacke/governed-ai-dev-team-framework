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
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Assess adoption conflicts for a target repository without modifying it. "
            "Not preflight, diagnose, or gate G0. Hybrid governance is not supported."
        )
    )
    parser.add_argument("--target", required=True, help="Path to the candidate project root")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # Avoid Windows cp1252 failures on JSON/human reports.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    target = Path(args.target).expanduser().resolve()
    resolutions = None
    if args.resolutions:
        try:
            resolutions = load_resolutions_file(Path(args.resolutions))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Invalid --resolutions file: {exc}", file=sys.stderr)
            return 1

    try:
        report = run_assessment(target, source_root=SOURCE_ROOT, resolutions=resolutions)
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
