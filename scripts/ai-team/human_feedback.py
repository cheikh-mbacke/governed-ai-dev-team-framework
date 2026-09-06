#!/usr/bin/env python3
"""Record asynchronous human UI feedback against an observed commit."""

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

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed

RESULTS = frozenset({"passed", "failed", "not_run", "not_applicable"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_bundle_version(ai_team: Path) -> str:
    pointer = ai_team / "contracts" / "active-bundle.json"
    try:
        return str(json.loads(pointer.read_text(encoding="utf-8"))["bundle_version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return "1.0.0"


def _scenario(value: str) -> dict[str, str | None]:
    scenario_id, separator, result = value.partition("=")
    if not separator or not scenario_id.strip() or result not in RESULTS:
        choices = ", ".join(sorted(RESULTS))
        raise argparse.ArgumentTypeError(f"expected SCENARIO=RESULT where RESULT is one of: {choices}")
    return {"scenario_id": scenario_id.strip(), "result": result, "notes": None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Record non-blocking formative UI feedback. This does not approve G4 "
            "or pause an unattended Run."
        )
    )
    parser.add_argument("--work-unit", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--sha", required=True, help="exact 40-character commit SHA tested")
    parser.add_argument("--comment", required=True)
    parser.add_argument("--by", required=True, help="human submitting the feedback")
    parser.add_argument("--checkpoint", default=None, help="checkpoint event id")
    parser.add_argument("--acceptance-package", default=None)
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        type=_scenario,
        metavar="SCENARIO=RESULT",
    )
    parser.add_argument("--feedback-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
    except GatewayError as exc:
        print(exc.message, file=sys.stderr)
        return exit_code_for(exc.code)

    feedback_id = args.feedback_id or f"HF-{uuid.uuid4().hex[:12].upper()}"
    key = uuid.uuid4().hex
    now = _now_iso()
    envelope = {
        "protocol_version": "1.0",
        "command_id": f"CMD-human-feedback-{key}",
        "idempotency_key": f"human-feedback-{key}",
        "correlation_id": f"COR-human-feedback-{key}",
        "type": "RecordHumanFeedback",
        "issued_at": now,
        "actor": {
            "kind": "role",
            "execution_id": f"EXE-human-feedback-{key[:8]}",
            "role_id": "control-plane",
            "bundle_version": _active_bundle_version(workspace.ai_team),
            "adapter_id": "cursor",
        },
        "target": {"kind": "human_feedback", "id": feedback_id},
        "payload": {
            "id": feedback_id,
            "checkpoint_ref": args.checkpoint,
            "acceptance_package_ref": args.acceptance_package,
            "work_unit": args.work_unit,
            "surface": args.surface,
            "observed_revision": {
                "commit_sha": args.sha,
                "captured_at": now,
                "evidence_refs": [],
            },
            "scenario_results": args.scenario,
            "comment": args.comment,
            "submitted_by": args.by,
        },
        "human_authorization": {
            "authorization_id": f"HAUTH-{uuid.uuid4().hex[:16].upper()}",
            "granted_by": args.by,
            "granted_at": now,
            "scope": f"human-feedback:{feedback_id}",
            "consumed_at": None,
        },
    }
    receipt, exit_code = CommandGateway(workspace).execute_command(envelope)
    json.dump(receipt, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if exit_code == 0:
        print(
            "Feedback recorded without pausing execution; the Control Plane will "
            "reconcile it before the next affected dispatch.",
            file=sys.stderr,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
