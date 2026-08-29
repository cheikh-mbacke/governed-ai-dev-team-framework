#!/usr/bin/env python3
"""Record an explicit human gate decision in Project State and decisions/.

Example:
  python scripts/ai-team/record_gate.py G1 approved --by alice --note "Plan accepted" \\
    --authorization-id HAUTH-g1-alice

For G4 specifically, this does NOT by itself mark any Work Unit's own
Definition of Done as satisfied - project-state.yaml (this script) and a
Work Unit's own outcomes.human_acceptance (checked by check_done.py) are
two different files. Pass --work-unit to also update the Work Unit(s):

  python scripts/ai-team/record_gate.py G4 accepted --by alice --work-unit WU-006 \\
    --authorization-id HAUTH-g4-wu006
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

try:
    from governed_ai.core.commands.errors import EXIT_CLI, exit_code_for
    from governed_ai.core.commands.gateway import CommandGateway
    from governed_ai.core.commands.legacy_cli import (
        DEPRECATION_RECORD_GATE,
        RecordGateArgs,
        TranslationError,
        format_record_gate_stdout,
        translate_record_gate,
    )
    from governed_ai.core.workspace import Workspace
except ModuleNotFoundError:
    print("Missing dependency: PyYAML/jsonschema. Install requirements first.", file=sys.stderr)
    raise SystemExit(1) from None

parser = argparse.ArgumentParser()
parser.add_argument("gate", choices=sorted({"G0", "G1", "G2", "G3", "G4"}))
parser.add_argument(
    "status",
    choices=sorted(
        {
            "approved",
            "rejected",
            "changes_requested",
            "passed",
            "failed",
            "partial",
            "partially_accepted",
            "not_required",
            "accepted",
            "remediation_required",
        }
    ),
)
parser.add_argument("--by", required=True)
parser.add_argument("--note", default="")
parser.add_argument(
    "--work-unit",
    default="",
    help="Comma-separated Work Unit id(s) this gate decision applies to (mainly G4).",
)
parser.add_argument(
    "--authorization-id",
    default="",
    help="Human authorization id required by the Command Gateway.",
)
parser.add_argument("--authorization-granted-by", default="")
parser.add_argument("--authorization-scope", default="")
args = parser.parse_args()

print(DEPRECATION_RECORD_GATE, file=sys.stderr)

try:
    envelope = translate_record_gate(
        RecordGateArgs(
            gate=args.gate,
            status=args.status,
            by=args.by,
            note=args.note,
            work_unit=args.work_unit,
            authorization_id=args.authorization_id,
            authorization_granted_by=args.authorization_granted_by,
            authorization_scope=args.authorization_scope,
        )
    )
except TranslationError as exc:
    print(f"WRAPPER TRANSLATION ERROR: {exc}", file=sys.stderr)
    raise SystemExit(EXIT_CLI) from exc

workspace = Workspace.discover(Path.cwd())
gateway = CommandGateway(workspace)
receipt, exit_code = gateway.execute_command(envelope)
if exit_code != 0:
    errors = receipt.get("errors") or []
    message = errors[0]["message"] if errors else "gateway rejected the command"
    print(f"GATEWAY ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)

for line in format_record_gate_stdout(receipt, by=args.by):
    print(line)
