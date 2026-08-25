#!/usr/bin/env python3
"""Propose allowlist additions derived from this project's declared commands.

Read-only: this never writes .cursor/permissions.json or .cursor/cli.json —
agents are denied write access to both (see .cursor/cli.json "deny"), and an
agent proposing itself broader execution rights is exactly the kind of
self-expanding autonomy 00-authority.yaml rules out. This script only prints
a diff for a human to review and apply, scoped to exactly the commands
recorded in project-profile.yaml. It never proposes a bare per-tool wildcard
(e.g. Shell(make:*)) — only the literal declared command, so a future
Makefile target like "make deploy-prod" is never auto-covered by an old
proposal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    print(
        "Missing dependency: PyYAML. Install it first, then re-run this command:"
    )
    print("  pip install -r requirements.txt")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"
CURSOR = ROOT / ".cursor"

COMMAND_FIELDS = [
    "setup",
    "build",
    "lint",
    "typecheck",
    "unit_test",
    "integration_test",
    "e2e_test",
]


def load_yaml(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def declared_commands(profile: dict) -> dict:
    commands = (profile or {}).get("commands") or {}
    result = {}
    for field in COMMAND_FIELDS:
        value = commands.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = value.strip()
    return result


COMPOUND_MARKERS = ("&&", "||", ";", "|", ">", "<")


def is_compound(command: str) -> bool:
    return any(marker in command for marker in COMPOUND_MARKERS)


def cli_token(command: str) -> str:
    tool, _, rest = command.partition(" ")
    rest = rest.strip()
    return f"Shell({tool}:{rest}*)" if rest else f"Shell({tool}:*)"


def build_proposals(profile: dict, ui_config: dict, cli_config: dict) -> list:
    existing_terminal = set(ui_config.get("terminalAllowlist") or [])
    existing_cli_allow = set((cli_config.get("permissions") or {}).get("allow") or [])

    proposals = []
    seen_commands = set()
    for field, command in declared_commands(profile).items():
        if command in seen_commands:
            continue
        seen_commands.add(command)
        entry = {
            "source_field": field,
            "command": command,
            "terminal_allowlist_entry": command,
            "terminal_allowlist_already_present": command in existing_terminal,
        }
        if is_compound(command):
            # "cd frontend && pnpm test:e2e" has no single binary to key a
            # Shell(tool:args) token on - splitting on the first space would
            # propose Shell(cd:...), which is meaningless. Flag it for the
            # human to author by hand instead of guessing.
            entry["cli_allow_token"] = None
            entry["cli_allow_already_present"] = False
            entry["cli_allow_note"] = (
                "compound command (shell operator present) - author the Shell() "
                "token(s) yourself, one per stage if needed"
            )
        else:
            token = cli_token(command)
            entry["cli_allow_token"] = token
            entry["cli_allow_already_present"] = token in existing_cli_allow
        proposals.append(entry)
    return proposals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propose allowlist additions derived from project-profile.yaml commands"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    profile = load_yaml(AI / "project-profile.yaml")
    if profile is None:
        note = "No .ai-team/project-profile.yaml found - nothing to propose."
        print(json.dumps({"proposals": [], "note": note}) if args.json else note)
        return 0

    commands = declared_commands(profile)
    if not commands:
        note = "No commands declared yet in project-profile.yaml - nothing to propose."
        print(json.dumps({"proposals": [], "note": note}) if args.json else note)
        return 0

    ui_config = load_json(CURSOR / "permissions.json") or {}
    cli_config = load_json(CURSOR / "cli.json") or {}
    proposals = build_proposals(profile, ui_config, cli_config)

    new_terminal = [
        p["terminal_allowlist_entry"] for p in proposals if not p["terminal_allowlist_already_present"]
    ]
    new_cli = [
        p["cli_allow_token"]
        for p in proposals
        if p["cli_allow_token"] and not p["cli_allow_already_present"]
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
        for p in needs_manual_review:
            print(f"  {p['command']!r}: {p['cli_allow_note']}")

    print(
        "\nThis is a proposal, not an application: review each entry against its "
        "source command below, then edit the two files yourself (agents cannot "
        "write them). Never widen a token beyond the exact declared command - "
        "no bare tool-level wildcard."
    )
    print("\nSource commands:")
    for p in proposals:
        print(f"  {p['source_field']:18s} -> {p['command']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
