#!/usr/bin/env python3
"""Inspect, dispatch or test non-blocking SMTP notifications."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed
from governed_ai.notifications.config import load_smtp_settings, public_smtp_status
from governed_ai.notifications.service import dispatch_notifications, send_test_notification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show public SMTP configuration, never the password")
    subparsers.add_parser("dispatch", help="send immediate queued notifications")
    subparsers.add_parser("digest", help="send immediate notifications and one grouped digest")
    subparsers.add_parser(
        "configure-secret",
        help="store the SMTP password in the local gitignored secret file",
    )
    test_parser = subparsers.add_parser("test", help="send a harmless SMTP test message")
    test_parser.add_argument("--to", default=None, help="test recipient; defaults to configured group")
    return parser


def _configure_secret(workspace: Workspace) -> dict[str, object]:
    password = os.environ.get("GOVERNED_AI_SMTP_PASSWORD")
    source = "environment"
    if not password:
        password = getpass.getpass("SMTP password: ")
        source = "interactive_prompt"
    if not password:
        return {"configured": False, "error": "empty password"}
    secrets_dir = workspace.ai_team / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    gitignore = secrets_dir / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
    path = secrets_dir / "smtp.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"password": password}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return {
        "configured": True,
        "source": source,
        "path": ".ai-team/secrets/smtp.json",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
    except GatewayError as exc:
        print(exc.message, file=sys.stderr)
        return exit_code_for(exc.code)

    if args.command == "configure-secret":
        result = _configure_secret(workspace)
    elif args.command == "status":
        result = public_smtp_status(load_smtp_settings(workspace.ai_team))
    elif args.command == "test":
        result = send_test_notification(workspace, recipient=args.to)
    else:
        result = dispatch_notifications(workspace, include_digest=args.command == "digest")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if args.command == "test" and not result.get("sent"):
        return 1
    if args.command == "configure-secret" and not result.get("configured"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
