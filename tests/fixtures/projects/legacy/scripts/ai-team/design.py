#!/usr/bin/env python3
"""Design Authority CLI — register, compile, bind, verify, reconcile."""

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

from governed_ai.core.commands.errors import ErrorCode, GatewayError, exit_code_for
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.design_authority.hashing import sha256_file
from governed_ai.core.design_authority.registry import (
    load_artifact,
    verify_artifact_integrity,
)
from governed_ai.core.design_authority.status import design_status
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


def _load_authorization(workspace: Workspace, authorization_id: str) -> dict:
    path = workspace.ai_team / "authorizations" / f"{authorization_id}.json"
    if not path.is_file():
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            f"authorization {authorization_id!r} not found under .ai-team/authorizations/",
            "/human_authorization/authorization_id",
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"authorization {authorization_id!r} is unreadable: {exc}",
            "/human_authorization/authorization_id",
        ) from exc
    if not isinstance(record, dict):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"authorization {authorization_id!r} must be an object",
            "/human_authorization/authorization_id",
        )
    if record.get("consumed_at"):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"authorization {authorization_id!r} already consumed",
            "/human_authorization/authorization_id",
        )
    return record


def _envelope(
    command_type: str,
    *,
    target: dict,
    payload: dict,
    role_id: str = "control-plane",
    human_by: str | None = None,
    authorization_id: str | None = None,
    authorization_record: dict | None = None,
    workspace: Workspace,
) -> dict:
    key = uuid.uuid4().hex
    now = _now_iso()
    env: dict = {
        "protocol_version": "1.0",
        "command_id": f"CMD-design-{key}",
        "idempotency_key": f"design-{command_type}-{key}",
        "correlation_id": f"COR-design-{key}",
        "type": command_type,
        "issued_at": now,
        "actor": {
            "kind": "role",
            "execution_id": f"EXE-design-{key[:8]}",
            "role_id": role_id,
            "bundle_version": _active_bundle_version(workspace.ai_team),
            "adapter_id": "cursor",
        },
        "target": target,
        "payload": payload,
    }
    if human_by and authorization_id:
        record = authorization_record or {}
        granted_by = str(record.get("granted_by") or human_by)
        scope = record.get("scope") or f"design:{command_type}:{target.get('id')}"
        env["human_authorization"] = {
            "authorization_id": authorization_id,
            "granted_by": granted_by,
            "granted_at": record.get("granted_at") or now,
            "scope": scope,
            "consumed_at": None,
        }
    return env


def _print(data: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(data)


def _require_authoritative_human_auth(args: argparse.Namespace, workspace: Workspace) -> dict:
    if not args.human or not args.authorization_id:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "authoritative operations require explicit --human and --authorization-id "
            "(never invent human_authorization from --by)",
            "/human_authorization",
        )
    if not str(args.human).startswith("human:"):
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "--human must start with human:",
            "/human_authorization/granted_by",
        )
    record = _load_authorization(workspace, args.authorization_id)
    granted = str(record.get("granted_by") or "").strip()
    if granted and granted != args.human:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"--human {args.human!r} does not match authorization granted_by {granted!r}",
            "/human_authorization/granted_by",
        )
    if not granted:
        record = {**record, "granted_by": args.human}
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Design Authority & Visual Conformance")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Register a design artifact")
    reg.add_argument("--id", required=True, help="DA-… identifier")
    reg.add_argument("--path", default=None, help="workspace-relative path")
    reg.add_argument("--uri", default=None, help="remote URI (e.g. Figma)")
    reg.add_argument("--local-mirror", default=None, help="local mirror for remote authoritative")
    reg.add_argument("--source-type", default=None)
    reg.add_argument(
        "--authority",
        default="advisory",
        choices=["authoritative", "advisory", "inspiration_only", "deprecated"],
    )
    reg.add_argument("--by", required=True, help="registrant (not used as human authorizer)")
    reg.add_argument("--content-pin", default=None, help="required for authoritative remotes")
    reg.add_argument("--screen", action="append", default=[])
    reg.add_argument("--state", action="append", default=[])
    reg.add_argument(
        "--human",
        default=None,
        help="human: authorizer (required for authoritative; never defaults from --by)",
    )
    reg.add_argument(
        "--authorization-id",
        default=None,
        help="existing unconsumed authorization under .ai-team/authorizations/",
    )

    auth = sub.add_parser("set-authority", help="Change design artifact authority level")
    auth.add_argument("--id", required=True)
    auth.add_argument(
        "--authority",
        required=True,
        choices=["authoritative", "advisory", "inspiration_only", "deprecated"],
    )
    auth.add_argument("--human", required=True, help="human: authorizer")
    auth.add_argument("--authorization-id", required=True)

    cref = sub.add_parser("create-reference-set", help="Group artifacts into a reference set")
    cref.add_argument("--id", required=True)
    cref.add_argument("--title", required=True)
    cref.add_argument(
        "--member",
        action="append",
        default=[],
        help="ARTIFACT_ID[=route:PATH][=state:NAME][=viewport:NAME]",
    )
    cref.add_argument("--by", required=True)

    comp = sub.add_parser("compile-contract", help="Compile a Design Contract")
    comp.add_argument("--id", required=True)
    comp.add_argument(
        "--mode",
        required=True,
        choices=["conform", "adapt", "create", "maintain", "explore"],
    )
    comp.add_argument("--reference-set", default=None)
    comp.add_argument("--route", action="append", default=[])
    comp.add_argument("--screen", action="append", default=[])
    comp.add_argument("--mandatory-text", action="append", default=[])
    comp.add_argument("--mandatory-element", action="append", default=[])
    comp.add_argument("--by", required=True)

    bind = sub.add_parser("bind-work-unit", help="Bind a Design Contract to a Work Unit")
    bind.add_argument("--work-unit", required=True)
    bind.add_argument("--contract", required=True)
    bind.add_argument("--mode", default=None)
    bind.add_argument("--reference-set", default=None)

    st = sub.add_parser("status", help="Show design registry status")
    st.add_argument("--artifact", default=None)

    ver = sub.add_parser("verify", help="Run visual conformance (observations via JSON file)")
    ver.add_argument("--report-id", required=True)
    ver.add_argument("--contract", required=True)
    ver.add_argument("--work-unit", required=True)
    ver.add_argument("--sha", required=True)
    ver.add_argument("--verifier-role", default="visual-qa")
    ver.add_argument("--implementer-role", default="frontend-developer")
    ver.add_argument("--observations", required=True, help="JSON file of observations")
    ver.add_argument("--agent-claimed-passed", action="store_true")

    diff = sub.add_parser("diff", help="Compare artifact integrity / hashes")
    diff.add_argument("--artifact", required=True)

    rec = sub.add_parser("reconcile", help="Reconcile a new mockup revision")
    rec.add_argument("--id", required=True)
    rec.add_argument("--previous", required=True)
    rec.add_argument("--new", required=True)
    rec.add_argument("--by", required=True)

    return parser


def _parse_member(raw: str) -> dict:
    parts = raw.split("=")
    member: dict = {"design_artifact_id": parts[0], "target": {}}
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        member["target"][key] = value
    return member


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
    except GatewayError as exc:
        # Fabrication repo: allow design tooling against payload schemas for
        # framework tests; installed clients still enforce the gate.
        if "framework_source" not in str(exc.message):
            print(exc.message, file=sys.stderr)
            return exit_code_for(exc.code)

    gateway = CommandGateway(workspace)
    as_json = bool(args.json)

    try:
        if args.command == "register":
            human = None
            authorization_id = None
            auth_record = None
            if args.authority == "authoritative":
                auth_record = _require_authoritative_human_auth(args, workspace)
                human = args.human
                authorization_id = args.authorization_id
            payload = {
                "design_artifact_id": args.id,
                "authority_level": args.authority,
                "registered_by": args.by,
                "source_type": args.source_type,
                "screens": args.screen,
                "states": args.state,
                "content_pin": args.content_pin,
            }
            if args.uri:
                payload["source_uri"] = args.uri
            if args.path:
                payload["source_path"] = args.path
            if args.local_mirror:
                payload["local_mirror_path"] = args.local_mirror
            receipt, code = gateway.execute_command(
                _envelope(
                    "RegisterDesignArtifact",
                    target={"kind": "design_artifact", "id": args.id},
                    payload=payload,
                    human_by=human,
                    authorization_id=authorization_id,
                    authorization_record=auth_record,
                    workspace=workspace,
                )
            )
            _print(receipt if as_json else {"status": receipt.get("status"), "id": args.id, "exit": code}, as_json=as_json)
            return code

        if args.command == "set-authority":
            auth_record = _require_authoritative_human_auth(args, workspace)
            receipt, code = gateway.execute_command(
                _envelope(
                    "SetDesignArtifactAuthority",
                    target={"kind": "design_artifact", "id": args.id},
                    payload={
                        "design_artifact_id": args.id,
                        "authority_level": args.authority,
                    },
                    human_by=args.human,
                    authorization_id=args.authorization_id,
                    authorization_record=auth_record,
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

        if args.command == "create-reference-set":
            members = [_parse_member(m) for m in args.member]
            receipt, code = gateway.execute_command(
                _envelope(
                    "CreateDesignReferenceSet",
                    target={"kind": "design_reference_set", "id": args.id},
                    payload={
                        "design_reference_set_id": args.id,
                        "title": args.title,
                        "members": members,
                        "created_by": args.by,
                    },
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

        if args.command == "compile-contract":
            receipt, code = gateway.execute_command(
                _envelope(
                    "CompileDesignContract",
                    target={"kind": "design_contract", "id": args.id},
                    payload={
                        "design_contract_id": args.id,
                        "design_mode": args.mode,
                        "design_reference_set_id": args.reference_set,
                        "routes": args.route,
                        "screens": args.screen,
                        "mandatory_text": args.mandatory_text,
                        "mandatory_elements": args.mandatory_element,
                        "compiled_by": args.by,
                    },
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

        if args.command == "bind-work-unit":
            receipt, code = gateway.execute_command(
                _envelope(
                    "BindDesignToWorkUnit",
                    target={"kind": "work_unit", "id": args.work_unit},
                    payload={
                        "work_unit_id": args.work_unit,
                        "design_contract_id": args.contract,
                        "design_mode": args.mode,
                        "design_reference_set_id": args.reference_set,
                    },
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

        if args.command == "status":
            if args.artifact:
                art = load_artifact(workspace, args.artifact)
                integrity = verify_artifact_integrity(workspace, art)
                _print({"artifact": art, "integrity": integrity}, as_json=as_json)
            else:
                _print(design_status(workspace), as_json=as_json)
            return 0

        if args.command == "verify":
            observations = json.loads(Path(args.observations).read_text(encoding="utf-8"))
            receipt, code = gateway.execute_command(
                _envelope(
                    "RecordVisualConformance",
                    target={"kind": "visual_conformance_report", "id": args.report_id},
                    payload={
                        "report_id": args.report_id,
                        "design_contract_id": args.contract,
                        "work_unit_id": args.work_unit,
                        "commit_sha": args.sha,
                        "verifier_role": args.verifier_role,
                        "implementer_role": args.implementer_role,
                        "observations": observations,
                        "agent_claimed_passed": bool(args.agent_claimed_passed),
                    },
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

        if args.command == "diff":
            art = load_artifact(workspace, args.artifact)
            integrity = verify_artifact_integrity(workspace, art)
            payload = {
                "design_artifact_id": args.artifact,
                "registered_hash": art.get("content_hash"),
                "integrity": integrity,
            }
            if art.get("source_path"):
                path = workspace.root / str(art["source_path"])
                if path.is_file():
                    payload["current_hash"] = sha256_file(path)
            _print(payload, as_json=as_json)
            return 0 if integrity.get("ok") else 1

        if args.command == "reconcile":
            receipt, code = gateway.execute_command(
                _envelope(
                    "ReconcileDesignRevision",
                    target={"kind": "design_reconciliation", "id": args.id},
                    payload={
                        "reconciliation_id": args.id,
                        "previous_artifact_id": args.previous,
                        "new_artifact_id": args.new,
                        "triggered_by": args.by,
                    },
                    workspace=workspace,
                )
            )
            _print(receipt, as_json=as_json)
            return code

    except GatewayError as exc:
        print(exc.message, file=sys.stderr)
        return exit_code_for(exc.code)

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
