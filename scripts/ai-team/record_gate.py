#!/usr/bin/env python3
"""Record an explicit human gate decision in Project State and decisions/.

Example:
  python scripts/ai-team/record_gate.py G1 approved --by alice --note "Plan accepted"

For G4 specifically, this does NOT by itself mark any Work Unit's own
Definition of Done as satisfied - project-state.yaml (this script) and a
Work Unit's own outcomes.human_acceptance (checked by check_done.py) are
two different files. Pass --work-unit to also update the Work Unit(s):

  python scripts/ai-team/record_gate.py G4 accepted --by alice --work-unit WU-006
  python scripts/ai-team/record_gate.py G4 accepted --by alice --work-unit WU-006,WU-007
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
parser.add_argument("status", choices=["approved","rejected","changes_requested","passed","failed","partial","partially_accepted","not_required","accepted","remediation_required"])
parser.add_argument("--by", required=True)
parser.add_argument("--note", default="")
parser.add_argument("--work-unit", default="", help="Comma-separated Work Unit id(s) this gate decision applies to (mainly G4). Updates each one's outcomes.human_acceptance so check_done.py reflects it.")
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
elif args.gate == "G4" and args.status in ("approved", "passed", "accepted"):
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
decisions_dir = AI / "decisions"
decisions_dir.mkdir(parents=True, exist_ok=True)
out = decisions_dir / f"gate-{args.gate.lower()}-{now[:10]}-{now[11:19].replace(':','')}.yaml"
out.write_text(yaml.safe_dump(decision, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"Recorded {args.gate}={args.status} by {args.by}")

if args.gate == "G4" and args.work_unit:
    outcome_map = {
        "approved": "accepted", "passed": "accepted", "accepted": "accepted",
        "rejected": "rejected", "failed": "rejected",
        "partial": "partially_accepted", "partially_accepted": "partially_accepted", "changes_requested": "partially_accepted",
        "remediation_required": "remediation_required",
        "not_required": "accepted",
    }
    human_acceptance_value = outcome_map.get(args.status, args.status)
    wu_dir = AI / "work-units"

    def find_work_unit_path(wu_dir: Path, wu_id: str):
        exact = wu_dir / f"{wu_id}.yaml"
        if exact.exists():
            return exact, None
        prefix_matches = sorted(wu_dir.glob(f"{wu_id}-*.yaml"))
        if len(prefix_matches) == 1:
            return prefix_matches[0], None
        if len(prefix_matches) > 1:
            return None, f"multiple files match '{wu_id}-*.yaml': {[p.name for p in prefix_matches]}"
        for p in sorted(wu_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("id") == wu_id:
                return p, None
        return None, None

    for wu_id in [w.strip() for w in args.work_unit.split(",") if w.strip()]:
        wu_path, ambiguity = find_work_unit_path(wu_dir, wu_id)
        if ambiguity:
            print(f"  WARN: {ambiguity} - skipped, nothing updated for it")
            continue
        if wu_path is None:
            print(f"  WARN: no file found for Work Unit id '{wu_id}' under .ai-team/work-units/ - skipped, nothing updated for it")
            continue
        wu = yaml.safe_load(wu_path.read_text(encoding="utf-8")) or {}
        wu.setdefault("outcomes", {})["human_acceptance"] = human_acceptance_value

        # Recording G4 resolves any critical_open_items that were only ever
        # tracking "waiting for human acceptance/G4" - leaving them in place
        # would otherwise block DONE forever on a note this same command just
        # resolved. Only items clearly about human acceptance/G4 are removed;
        # anything else (a real defect, an audit finding) is left untouched -
        # this command isn't authority to resolve those.
        import re
        remaining, cleared = [], []
        for item in wu["outcomes"].get("critical_open_items") or []:
            text = str(item).lower()
            if "human_acceptance" in text or "human acceptance" in text or re.search(r"\bg4\b", text):
                cleared.append(item)
            else:
                remaining.append(item)
        wu["outcomes"]["critical_open_items"] = remaining

        wu_path.write_text(yaml.safe_dump(wu, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"  Updated {wu_path.name}: outcomes.human_acceptance = {human_acceptance_value}")
        if cleared:
            print(f"  Cleared {len(cleared)} critical_open_items resolved by this G4 decision: {cleared}")
    print("  Run python scripts/ai-team/check_done.py <WU-ID> to confirm each Work Unit's overall Definition of Done.")
elif args.gate == "G4" and not args.work_unit:
    print("  NOTE: no --work-unit given. This recorded the gate at the project level only -")
    print("  it did NOT mark any specific Work Unit's human_acceptance. If a Work Unit needs")
    print("  that recorded too, re-run with --work-unit WU-XXX, or check_done.py will still")
    print("  report it as NOT DONE.")
