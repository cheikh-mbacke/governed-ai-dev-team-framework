#!/usr/bin/env python3
"""Register ensembles, members, and composition revisions (Document 25)."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.errors import (
    EXIT_CLI,
    EXIT_INTERNAL,
    ErrorCode,
    GatewayError,
    exit_code_for,
)
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_bundle_version(ai_team: Path) -> str:
    pointer = ai_team / "contracts" / "active-bundle.json"
    try:
        return str(json.loads(pointer.read_text(encoding="utf-8"))["bundle_version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return "1.0.0"


def _envelope(command_type: str, *, target: dict, payload: dict, workspace: Workspace) -> dict:
    key = uuid.uuid4().hex
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-ensemble-{key}",
        "idempotency_key": f"ensemble-{command_type}-{key}",
        "correlation_id": f"COR-ensemble-{key}",
        "type": command_type,
        "issued_at": _now_iso(),
        "actor": {
            "kind": "role",
            "execution_id": f"EXE-ensemble-{key[:8]}",
            "role_id": "control-plane",
            "bundle_version": _active_bundle_version(workspace.ai_team),
            "adapter_id": "cursor",
        },
        "target": target,
        "payload": payload,
    }


def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _execute(workspace: Workspace, envelope: dict) -> int:
    receipt, exit_code = CommandGateway(workspace).execute_command(envelope)
    _emit(receipt)
    return exit_code


def _load_members_revision(workspace: Workspace, ensemble_id: str) -> int:
    path = workspace.ensembles_root / ensemble_id / "members.yaml"
    if not path.is_file():
        return 1
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return int(document.get("revision") or 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instance ensemble commands")
    sub = parser.add_subparsers(dest="command", required=True)

    register_ensemble = sub.add_parser("register-ensemble", help="Register an ensemble")
    register_ensemble.add_argument("--id", required=True)
    register_ensemble.add_argument("--name")
    register_ensemble.add_argument("--docs-path")

    register_member = sub.add_parser("register-member", help="Register a member Git path")
    register_member.add_argument("--ensemble", required=True)
    register_member.add_argument("--id", required=True)
    register_member.add_argument("--kind", required=True)
    register_member.add_argument("--path", required=True)
    register_member.add_argument("--origin")
    register_member.add_argument(
        "--expected-revision",
        type=int,
        default=None,
        help="members.yaml revision; defaults to the current file revision",
    )

    pin = sub.add_parser("pin-composition", help="Pin a composition revision")
    pin.add_argument("--ensemble", required=True)
    pin.add_argument("--id", required=True)
    pin.add_argument(
        "--member",
        action="append",
        default=[],
        metavar="ID=SHA",
        help="Explicit member SHA (repeatable). Omit to snapshot HEAD of every member.",
    )

    active = sub.add_parser("set-active", help="Select the active ensemble")
    active.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
        if args.command == "register-ensemble":
            payload: dict = {"id": args.id}
            if args.name:
                payload["name"] = args.name
            if args.docs_path:
                payload["docs_path"] = args.docs_path
            return _execute(
                workspace,
                _envelope(
                    "RegisterEnsemble",
                    target={"kind": "ensemble", "id": args.id},
                    payload=payload,
                    workspace=workspace,
                ),
            )
        if args.command == "register-member":
            revision = args.expected_revision
            if revision is None:
                revision = _load_members_revision(workspace, args.ensemble)
            payload = {"id": args.id, "kind": args.kind, "path": args.path}
            if args.origin:
                payload["origin"] = args.origin
            return _execute(
                workspace,
                _envelope(
                    "RegisterMember",
                    target={
                        "kind": "ensemble",
                        "id": args.ensemble,
                        "expected_revision": revision,
                    },
                    payload=payload,
                    workspace=workspace,
                ),
            )
        if args.command == "pin-composition":
            payload = {"id": args.id, "ensemble_id": args.ensemble}
            if args.member:
                members: dict[str, str] = {}
                for item in args.member:
                    if "=" not in item:
                        raise GatewayError(
                            ErrorCode.INVALID_SCHEMA,
                            "each --member must be ID=SHA",
                            "/payload/members",
                        )
                    member_id, sha = item.split("=", 1)
                    members[member_id] = sha
                payload["members"] = members
            return _execute(
                workspace,
                _envelope(
                    "PinComposition",
                    target={"kind": "composition", "id": args.id},
                    payload=payload,
                    workspace=workspace,
                ),
            )
        if args.command == "set-active":
            return _execute(
                workspace,
                _envelope(
                    "SetActiveEnsemble",
                    target={"kind": "ensemble", "id": args.id},
                    payload={"ensemble_id": args.id},
                    workspace=workspace,
                ),
            )
    except GatewayError as exc:
        _emit(
            {
                "command_id": "CMD-unknown",
                "status": "rejected",
                "errors": [exc.as_dict()],
            }
        )
        return exit_code_for(exc.code)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return EXIT_INTERNAL
    return EXIT_CLI


if __name__ == "__main__":
    raise SystemExit(main())
