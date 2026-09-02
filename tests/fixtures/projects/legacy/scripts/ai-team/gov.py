#!/usr/bin/env python3
"""Stable Command Gateway CLI (Document 11 §6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.errors import (
    EXIT_CLI,
    EXIT_INTERNAL,
    GatewayError,
    exit_code_for,
)
from governed_ai.core.commands.gateway import CommandGateway, load_envelope_from_json
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed


def _reject_client_cycle_on_fabrication(workspace: Workspace) -> None:
    ensure_client_cycle_allowed(workspace)


def _emit_json(payload: dict, *, file=sys.stdout) -> None:
    json.dump(payload, file, indent=2)
    file.write("\n")
    file.flush()


def _emit_error(message: str) -> None:
    print(message, file=sys.stderr)


def _cmd_command(args: argparse.Namespace) -> int:
    workspace = Workspace.discover(Path.cwd())
    try:
        _reject_client_cycle_on_fabrication(workspace)
    except GatewayError as exc:
        _emit_error(exc.message)
        return exit_code_for(exc.code)
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    gateway = CommandGateway(workspace)
    try:
        envelope = load_envelope_from_json(text)
    except GatewayError as exc:
        receipt = {
            "command_id": "CMD-unknown",
            "transaction_id": None,
            "status": "rejected",
            "affected": [],
            "domain_events": [],
            "errors": [exc.as_dict()],
        }
        _emit_json(receipt)
        return exit_code_for(exc.code)

    receipt, exit_code = gateway.execute_command(envelope)
    _emit_json(receipt)
    return exit_code


def _cmd_query(args: argparse.Namespace) -> int:
    workspace = Workspace.discover(Path.cwd())
    try:
        _reject_client_cycle_on_fabrication(workspace)
    except GatewayError as exc:
        _emit_error(exc.message)
        _emit_json(
            {
                "status": "rejected",
                "errors": [exc.as_dict()],
            }
        )
        return exit_code_for(exc.code)
    gateway = CommandGateway(workspace)
    try:
        result = gateway.query(args.name)
    except GatewayError as exc:
        _emit_error(exc.message)
        _emit_json(
            {
                "status": "rejected",
                "errors": [exc.as_dict()],
            }
        )
        return exit_code_for(exc.code)
    _emit_json(result)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    workspace = Workspace.discover(Path.cwd())
    gateway = CommandGateway(workspace)
    result = gateway.validate_gateway()
    if args.all:
        from governed_ai.contracts.compatibility import resolve_active_bundle_dir
        from governed_ai.contracts.validate_bundle import validate_bundle

        bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
        bundle_result = validate_bundle(bundle_dir)
        result["bundle"] = {
            "accepted": bundle_result.accepted,
            "issues": [
                {"code": issue.code, "message": issue.message, "path": issue.path}
                for issue in bundle_result.issues
            ],
        }
    _emit_json(result)
    return 0 if result.get("status") == "ok" else 7


def _cmd_recover(args: argparse.Namespace) -> int:
    workspace = Workspace.discover(Path.cwd())
    try:
        _reject_client_cycle_on_fabrication(workspace)
    except GatewayError as exc:
        _emit_error(exc.message)
        _emit_json({"status": "rejected", "errors": [exc.as_dict()]})
        return exit_code_for(exc.code)
    gateway = CommandGateway(workspace)
    result = gateway.recover()
    _emit_json(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Governance Command Gateway")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("command", help="Execute an authoritative command")
    cmd.add_argument("--input", help="Path to command envelope JSON")

    query = sub.add_parser("query", help="Run a read-only query")
    query.add_argument("name", help="Query name, e.g. project-state")

    validate = sub.add_parser("validate", help="Validate gateway and optional bundle state")
    validate.add_argument("--all", action="store_true", help="Include bundle validation")

    sub.add_parser("recover", help="Recover interrupted transactions")

    args = parser.parse_args(argv)
    try:
        if args.command == "command":
            return _cmd_command(args)
        if args.command == "query":
            return _cmd_query(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "recover":
            return _cmd_recover(args)
    except GatewayError as exc:
        _emit_error(exc.message)
        _emit_json({"status": "rejected", "errors": [exc.as_dict()]})
        return exit_code_for(exc.code)
    except Exception as exc:  # noqa: BLE001 — map unexpected failures to EXIT_INTERNAL
        _emit_error(str(exc))
        return EXIT_INTERNAL

    _emit_error("unknown command")
    return EXIT_CLI


if __name__ == "__main__":
    raise SystemExit(main())
