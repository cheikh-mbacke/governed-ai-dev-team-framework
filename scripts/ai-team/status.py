#!/usr/bin/env python3
from pathlib import Path
from collections import Counter

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

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

observations = []
for p in (AI / "observations").glob("*.yaml"):
    try:
        observations.append(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    except Exception:
        pass
unresolved = {"open", "acknowledged", "candidate_change"}
open_observations = [
    observation
    for observation in observations
    if observation.get("status") in unresolved
]
print(f"Open observations: {len(open_observations)}")
if open_observations:
    categories = Counter(
        observation.get("category", "unknown") for observation in open_observations
    )
    print(
        "  by category: "
        + ", ".join(f"{category}={count}" for category, count in sorted(categories.items()))
    )
