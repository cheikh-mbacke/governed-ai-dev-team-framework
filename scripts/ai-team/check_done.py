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

from i18n import project_language, t

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"
LANG = project_language(ROOT)

if len(sys.argv) != 2:
    print(t(LANG, "Usage: check_done.py WU-ID", "Usage : check_done.py WU-ID"))
    raise SystemExit(2)

wu_id = sys.argv[1]
wu_dir = AI / "work-units"


def find_work_unit_path(wu_dir: Path, wu_id: str):
    """Work Units are commonly named WU-XXX-description.yaml, not just
    WU-XXX.yaml - try the exact name first, then a WU-XXX-*.yaml prefix
    match, then fall back to reading each file's own id: field."""
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


path, ambiguity = find_work_unit_path(wu_dir, wu_id)
if ambiguity:
    print(t(LANG, f"Work Unit id '{wu_id}' is ambiguous: {ambiguity}", f"Identifiant de Work Unit '{wu_id}' ambigu : {ambiguity}"))
    raise SystemExit(2)
if path is None:
    print(t(LANG, f"Work Unit not found: {wu_id}", f"Work Unit introuvable : {wu_id}"))
    raise SystemExit(2)
wu = yaml.safe_load(path.read_text(encoding="utf-8"))
req = wu.get("required_verification", {})
missing = []

if not wu.get("evidence"):
    missing.append(t(LANG, "evidence", "preuves"))
if req.get("review") and not wu.get("outcomes", {}).get("review_status") == "approved":
    missing.append(t(LANG, "approved review", "revue approuvee"))
if req.get("audit") and not wu.get("outcomes", {}).get("audit_status") == "passed":
    missing.append(t(LANG, "required audit", "audit requis"))
if req.get("human_acceptance") and not wu.get("outcomes", {}).get("human_acceptance") in ("passed", "accepted"):
    missing.append(t(LANG, "human acceptance", "acceptation humaine"))
critical = wu.get("outcomes", {}).get("critical_open_items", [])
if critical:
    missing.append(t(
        LANG,
        "resolution/decision for critical open items",
        "resolution/decision pour les points critiques ouverts",
    ))

if missing:
    print(t(LANG, "NOT DONE", "PAS TERMINE"))
    for item in missing:
        print(t(LANG, f"- missing: {item}", f"- manquant : {item}"))
    raise SystemExit(1)
print(t(LANG, "DONE prerequisites recorded", "Prerequis de cloture enregistres"))
