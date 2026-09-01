#!/usr/bin/env python3
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

try:
    import yaml
except ModuleNotFoundError:
    from install_paths import requirements_install_hint

    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print(f"  {requirements_install_hint(_ROOT)}")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

from i18n import project_language, t

ROOT = _ROOT
AI = ROOT / ".ai-team"
LANG = project_language(ROOT)
state = yaml.safe_load((AI / "state" / "project-state.yaml").read_text(encoding="utf-8"))

print(t(LANG, "Project:", "Projet :") + f" {state.get('project_id')}")
print(t(LANG, "Phase:  ", "Phase :  ") + f" {state.get('phase')}")
print(t(LANG, "Gates:", "Gates :"))
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
    print(t(LANG, "Work Units:", "Unites de travail :"))
    for status, n in sorted(c.items()):
        print(f"  {status}: {n}")
else:
    print(t(LANG, "Work Units: none", "Unites de travail : aucune"))

print(t(LANG, "Open decisions:", "Decisions ouvertes :") + f" {len(state.get('open_decisions') or [])}")
print(t(LANG, "Open defects:  ", "Defauts ouverts :   ") + f" {len(state.get('open_defects') or [])}")
print(t(LANG, "Open findings: ", "Constats ouverts :  ") + f" {len(state.get('open_findings') or [])}")
print(t(LANG, "Active workers:", "Agents actifs :     ") + f" {len(state.get('active_workers') or [])}")

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
print(t(LANG, "Open observations:", "Constats d'apprentissage ouverts :") + f" {len(open_observations)}")
if open_observations:
    categories = Counter(
        observation.get("category", "unknown") for observation in open_observations
    )
    print(
        "  " + t(LANG, "by category: ", "par categorie : ")
        + ", ".join(f"{category}={count}" for category, count in sorted(categories.items()))
    )

checkpoints = {}
for p in sorted((AI / "events").glob("*.yaml")):
    try:
        event = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    if event.get("status") != "open":
        continue
    checkpoint = (event.get("details") or {}).get("human_checkpoint")
    if not checkpoint:
        continue
    # One line per Work Unit: keep the latest open checkpoint only.
    checkpoints[event.get("work_unit")] = (event.get("id"), checkpoint)
print(t(LANG, "Visual checkpoints available:", "Points de controle visuels disponibles :") + f" {len(checkpoints)}")
for work_unit, (event_id, checkpoint) in sorted(checkpoints.items(), key=lambda kv: kv[0] or ""):
    print(f"  {work_unit} ({event_id}): {checkpoint.get('command')}")
    print(f"    {checkpoint.get('why')}")
