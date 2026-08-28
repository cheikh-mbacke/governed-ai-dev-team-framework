"""Backward-compatible wrapper over governed_ai.core workspace and persistence helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

try:
    from governed_ai.core.persistence.io import dump_yaml, load_json, load_yaml
    from governed_ai.core.workspace import Workspace
except ModuleNotFoundError as exc:
    if exc.name in {"yaml", "PyYAML"}:
        print("Missing dependency: PyYAML. Install it first, then re-run this command:")
        print("  pip install -r requirements.txt")
        print("(or: pip install PyYAML jsonschema)")
        raise SystemExit(1) from exc
    raise

_workspace = Workspace.from_root(_REPO_ROOT)
ROOT = _workspace.root
AI = _workspace.ai_team

__all__ = ["ROOT", "AI", "load_yaml", "dump_yaml", "load_json"]
