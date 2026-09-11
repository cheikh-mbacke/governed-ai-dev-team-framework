#!/usr/bin/env python3
"""Inspect or update mutable Project Profile configuration."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.run.autonomy_policy import NAMED_AUTONOMY_PRESETS
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed


def _load_profile(workspace: Workspace) -> dict:
    path = workspace.ai_team / "project-profile.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Project Profile not found: {path}")
    profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile.setdefault("config_revision", 1)
    return profile


def _emit(value: dict) -> None:
    json.dump(value, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _execute_update(args: argparse.Namespace, changes: dict) -> int:
    workspace = Workspace.discover(Path.cwd())
    ensure_client_cycle_allowed(workspace)
    profile = _load_profile(workspace)
    token = uuid4().hex
    envelope = {
        "protocol_version": "1.0",
        "command_id": f"CMD-profile-{token}",
        "idempotency_key": f"profile-{token}",
        "correlation_id": f"COR-profile-{token}",
        "type": "UpdateProjectProfile",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "actor": {
            "kind": "role",
            "execution_id": f"EXE-profile-{token}",
            "role_id": "control-plane",
            "bundle_version": "1.0.0",
            "adapter_id": str(profile.get("active_adapter_id") or "cursor"),
        },
        "target": {
            "kind": "project_profile",
            "id": profile["project"]["id"],
            "expected_revision": profile["config_revision"],
        },
        "payload": {"changes": changes, "reason": args.reason},
        "human_authorization": {
            "authorization_id": f"AUTH-profile-{token}",
            "granted_by": args.authorized_by,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "scope": "UpdateProjectProfile",
        },
    }
    receipt, exit_code = CommandGateway(workspace).execute_command(envelope)
    _emit(receipt)
    return exit_code


def _cmd_show(_args: argparse.Namespace) -> int:
    workspace = Workspace.discover(Path.cwd())
    ensure_client_cycle_allowed(workspace)
    _emit({"status": "ok", "profile": _load_profile(workspace)})
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    patch = yaml.safe_load(Path(args.patch).read_text(encoding="utf-8"))
    if not isinstance(patch, dict) or not patch:
        raise ValueError("the patch file must contain a non-empty YAML object")
    return _execute_update(args, patch)


def _cmd_autonomy(args: argparse.Namespace) -> int:
    return _execute_update(args, {"autonomy": {"preset": args.preset}})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Governed Project Profile configuration (changes affect future Runs)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="Display the effective Project Profile")
    show.set_defaults(func=_cmd_show)

    apply_cmd = sub.add_parser("apply", help="Apply a YAML patch to mutable profile sections")
    apply_cmd.add_argument("--patch", required=True, help="Path to the YAML patch")
    apply_cmd.add_argument("--reason", required=True, help="Why this configuration changes")
    apply_cmd.add_argument("--authorized-by", required=True, help="Human authorizing the change")
    apply_cmd.set_defaults(func=_cmd_apply)

    autonomy = sub.add_parser("autonomy", help="Change the preset for future Runs")
    autonomy.add_argument("preset", choices=sorted(NAMED_AUTONOMY_PRESETS))
    autonomy.add_argument("--reason", required=True, help="Why this autonomy preset changes")
    autonomy.add_argument("--authorized-by", required=True, help="Human authorizing the change")
    autonomy.set_defaults(func=_cmd_autonomy)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - stable operator-facing error boundary
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
