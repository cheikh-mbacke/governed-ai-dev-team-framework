#!/usr/bin/env python3
from pathlib import Path
import yaml
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"
state = yaml.safe_load((AI / "state" / "project-state.yaml").read_text(encoding="utf-8"))

print(f"Project: {state.get('project_id')}")
print(f"Phase:   {state.get('phase')}")
print("Gates:")
for k, v in (state.get("gates") or {}).items():
    print(f"  {k}: {v.get('status') if isinstance(v, dict) else v}")

wus = []
for p in (AI / "work-units").glob("*.yaml"):
    try:
        wus.append(yaml.safe_load(p.read_text(encoding="utf-8")))
    except Exception:
        pass
if wus:
    c = Counter(w.get("status", "unknown") for w in wus)
    print("Work Units:")
    for status, n in sorted(c.items()):
        print(f"  {status}: {n}")
else:
    print("Work Units: none")

print(f"Open decisions: {len(state.get('open_decisions') or [])}")
print(f"Open defects:   {len(state.get('open_defects') or [])}")
print(f"Open findings:  {len(state.get('open_findings') or [])}")
print(f"Active workers: {len(state.get('active_workers') or [])}")
