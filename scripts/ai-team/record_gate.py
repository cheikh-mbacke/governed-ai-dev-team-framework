#!/usr/bin/env python3
"""Record an explicit human gate decision in Project State and decisions/.

Example:
  python scripts/ai-team/record_gate.py G1 approved --by alice --note "Plan accepted"
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

parser = argparse.ArgumentParser()
parser.add_argument("gate", choices=["G0","G1","G2","G3","G4"])
parser.add_argument("status", choices=["approved","rejected","changes_requested","passed","failed","partial","not_required"])
parser.add_argument("--by", required=True)
parser.add_argument("--note", default="")
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"
state_path = AI / "state" / "project-state.yaml"
state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
now = datetime.now(timezone.utc).isoformat()
state.setdefault("gates", {}).setdefault(args.gate, {})
state["gates"][args.gate] = {"status": args.status, "by": args.by, "at": now, "note": args.note}

if args.gate == "G1" and args.status == "approved":
    state["phase"] = "execution"
elif args.gate == "G0" and args.status in ("rejected", "failed", "changes_requested"):
    state["phase"] = "readiness_blocked"
elif args.gate == "G4" and args.status in ("approved", "passed"):
    state["phase"] = "completed"

state["last_updated"] = now
state_path.write_text(yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8")

decision = {
    "id": f"{args.gate}-{now.replace(':','').replace('+','_')}",
    "gate": args.gate,
    "status": args.status,
    "by": args.by,
    "at": now,
    "note": args.note,
}
out = AI / "decisions" / f"gate-{args.gate.lower()}-{now[:10]}-{now[11:19].replace(':','')}.yaml"
out.write_text(yaml.safe_dump(decision, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"Recorded {args.gate}={args.status} by {args.by}")
