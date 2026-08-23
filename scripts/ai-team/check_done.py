#!/usr/bin/env python3
"""Conservative Definition-of-Done checker for one Work Unit.

Usage: python scripts/ai-team/check_done.py WU-001
This intentionally errs on the side of NOT DONE when evidence is ambiguous.
"""
from pathlib import Path
import sys

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

if len(sys.argv) != 2:
    print("Usage: check_done.py WU-ID")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"
wu_id = sys.argv[1]
path = AI / "work-units" / f"{wu_id}.yaml"
if not path.exists():
    print(f"Work Unit not found: {wu_id}")
    raise SystemExit(2)
wu = yaml.safe_load(path.read_text(encoding="utf-8"))
req = wu.get("required_verification", {})
missing = []

if not wu.get("evidence"):
    missing.append("evidence")
if req.get("review") and not wu.get("outcomes", {}).get("review_status") == "approved":
    missing.append("approved review")
if req.get("audit") and not wu.get("outcomes", {}).get("audit_status") == "passed":
    missing.append("required audit")
if req.get("human_acceptance") and not wu.get("outcomes", {}).get("human_acceptance") in ("passed", "accepted"):
    missing.append("human acceptance")
critical = wu.get("outcomes", {}).get("critical_open_items", [])
if critical:
    missing.append("resolution/decision for critical open items")

if missing:
    print("NOT DONE")
    for item in missing:
        print(f"- missing: {item}")
    raise SystemExit(1)
print("DONE prerequisites recorded")
