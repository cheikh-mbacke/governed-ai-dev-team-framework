#!/usr/bin/env python3
"""Dependency-free preflight for Cursor UI/CLI governance hooks.

Generic Python/platform checks stay in this script; Cursor-specific probes
live in ``adapters.cursor.runtime``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime, import_adapters_cursor

bootstrap_runtime(ROOT)
_checks = import_adapters_cursor("runtime.checks")
collect_preflight_report = _checks.collect_preflight_report
from i18n import project_language, t

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed

LANG = project_language(ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Cursor CLI governance prerequisites")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--unattended",
        action="store_true",
        help="include checks required specifically for unattended execution",
    )
    args = parser.parse_args()
    try:
        ensure_client_cycle_allowed(Workspace.from_root(ROOT))
    except GatewayError as exc:
        print(exc.message)
        return exit_code_for(exc.code)
    report = collect_preflight_report(ROOT, unattended=args.unattended)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(t(LANG, "Governed AI Team preflight", "Verification prealable Governed AI Team"))
        print("=" * 26)
        print(f"platform: {report['platform']}")
        for name, result in report.items():
            if name == "platform":
                continue
            print(f"{result['status'].upper():8} {name}: {result['detail']}")
    blocking = {"fail", "blocked"}
    if args.unattended:
        # Document 6 §9.6 — align CLI exit code with Core OpenRun refusal.
        blocking.add("manual")
    return 1 if any(
        isinstance(result, dict) and result.get("status") in blocking
        for result in report.values()
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
