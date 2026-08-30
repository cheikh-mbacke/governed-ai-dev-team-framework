#!/usr/bin/env python3
"""Propose allowlist additions derived from this project's declared commands.

Read-only: this never writes .cursor/permissions.json or .cursor/cli.json.
Core reads project-profile commands; Cursor adapter reads permission files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import yaml  # noqa: F401 — dependency probe for PyYAML
except ModuleNotFoundError:
    _root = Path(__file__).resolve().parents[2]
    from install_paths import requirements_install_hint

    print(
        "Missing dependency: PyYAML. Install it first, then re-run this command:"
    )
    print(f"  {requirements_install_hint(_root)}")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime, import_adapters_cursor

bootstrap_runtime(ROOT)
_checks = import_adapters_cursor("runtime.checks")
build_allowlist_proposals = _checks.build_allowlist_proposals
load_cursor_json = _checks.load_cursor_json

from governed_ai.core.diagnostics import declared_profile_commands


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propose allowlist additions derived from project-profile.yaml commands"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    profile_path = ROOT / ".ai-team" / "project-profile.yaml"
    if not profile_path.is_file():
        note = "No .ai-team/project-profile.yaml found - nothing to propose."
        print(json.dumps({"proposals": [], "note": note}) if args.json else note)
        return 0

    commands = declared_profile_commands(ROOT)
    if not commands:
        note = "No commands declared yet in project-profile.yaml - nothing to propose."
        print(json.dumps({"proposals": [], "note": note}) if args.json else note)
        return 0

    ui_config = load_cursor_json(ROOT, ".cursor/permissions.json") or {}
    cli_config = load_cursor_json(ROOT, ".cursor/cli.json") or {}
    proposals = build_allowlist_proposals(commands, ui_config, cli_config)

    new_terminal = [
        p["terminal_allowlist_entry"] for p in proposals if not p["terminal_allowlist_already_present"]
    ]
    new_cli = [
        p["cli_allow_token"]
        for p in proposals
        if p.get("cli_allow_token") and not p["cli_allow_already_present"]
    ]
    needs_manual_review = [p for p in proposals if p.get("cli_allow_note")]

    if args.json:
        print(
            json.dumps(
                {
                    "proposals": proposals,
                    "terminal_allowlist_additions": new_terminal,
                    "cli_allow_additions": new_cli,
                    "cli_allow_needs_manual_review": [
                        {"command": p["command"], "note": p["cli_allow_note"]}
                        for p in needs_manual_review
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print("Proposed allowlist additions (derived from project-profile.yaml commands)")
    print("=" * 74)
    if not new_terminal and not new_cli:
        print("Nothing new: every declared command is already covered.")
        return 0

    print("\n.cursor/permissions.json -> terminalAllowlist (add):")
    for entry in new_terminal:
        print(f'  "{entry}",')

    print("\n.cursor/cli.json -> permissions.allow (add):")
    for token in new_cli:
        print(f'  "{token}",')

    if needs_manual_review:
        print("\nNeeds manual review (not proposed automatically):")
        for proposal in needs_manual_review:
            print(f"  {proposal['command']!r}: {proposal['cli_allow_note']}")

    print(
        "\nThis is a proposal, not an application: review each entry against its "
        "source command below, then edit the two files yourself (agents cannot "
        "write them). Never widen a token beyond the exact declared command - "
        "no bare tool-level wildcard."
    )
    print("\nSource commands:")
    for proposal in proposals:
        print(f"  {proposal['source_field']:18s} -> {proposal['command']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
