#!/usr/bin/env python3
"""Conservative Definition-of-Done checker for one Work Unit.

Usage: python scripts/ai-team/check_done.py WU-001
This intentionally errs on the side of NOT DONE when evidence is ambiguous.
"""
import sys
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
from install_paths import bootstrap_runtime

bootstrap_runtime(_ROOT)

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.domain.work_unit.done import missing_done_prerequisites
from governed_ai.core.domain.work_unit.paths import find_work_unit_path
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed

ROOT = _ROOT
LANG = project_language(ROOT)
WORKSPACE = Workspace.from_root(ROOT)
try:
    ensure_client_cycle_allowed(WORKSPACE)
except GatewayError as exc:
    print(exc.message, file=sys.stderr)
    raise SystemExit(exit_code_for(exc.code)) from None
AI = WORKSPACE.ai_team

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
