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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from governed_ai.core.domain.work_unit.done import missing_done_prerequisites
from governed_ai.core.domain.work_unit.paths import find_work_unit_path

ROOT = _REPO_ROOT
AI = ROOT / ".ai-team"
LANG = project_language(ROOT)

if len(sys.argv) != 2:
    print(t(LANG, "Usage: check_done.py WU-ID", "Usage : check_done.py WU-ID"))
    raise SystemExit(2)

wu_id = sys.argv[1]
wu_dir = AI / "work-units"

path, ambiguity = find_work_unit_path(wu_dir, wu_id)
if ambiguity:
    print(t(LANG, f"Work Unit id '{wu_id}' is ambiguous: {ambiguity}", f"Identifiant de Work Unit '{wu_id}' ambigu : {ambiguity}"))
    raise SystemExit(2)
if path is None:
    print(t(LANG, f"Work Unit not found: {wu_id}", f"Work Unit introuvable : {wu_id}"))
    raise SystemExit(2)
wu = yaml.safe_load(path.read_text(encoding="utf-8"))

_MISSING_LABELS = {
    "evidence": ("evidence", "preuves"),
    "approved review": ("approved review", "revue approuvee"),
    "required audit": ("required audit", "audit requis"),
    "human acceptance": ("human acceptance", "acceptation humaine"),
    "resolution/decision for critical open items": (
        "resolution/decision for critical open items",
        "resolution/decision pour les points critiques ouverts",
    ),
}

missing = missing_done_prerequisites(wu)

if missing:
    print(t(LANG, "NOT DONE", "PAS TERMINE"))
    for item in missing:
        en, fr = _MISSING_LABELS.get(item, (item, item))
        print(t(LANG, f"- missing: {en}", f"- manquant : {fr}"))
    raise SystemExit(1)
print(t(LANG, "DONE prerequisites recorded", "Prerequis de cloture enregistres"))
