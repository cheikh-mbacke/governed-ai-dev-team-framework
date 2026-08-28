"""Backward-compatible wrapper over governed_ai.feedback common helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

try:
    from governed_ai.core.workspace import Workspace
    from governed_ai.feedback import common as _common
except ModuleNotFoundError as exc:
    if exc.name in {"yaml", "PyYAML", "jsonschema"}:
        print("Missing dependency: PyYAML and/or jsonschema. Install requirements first.")
        raise SystemExit(1) from exc
    raise

_workspace = Workspace.from_root(_REPO_ROOT)
ROOT = _workspace.root
AI = _workspace.ai_team

now_utc = _common.now_utc
now_iso = _common.now_iso
generated_id = _common.generated_id
load_yaml = _common.load_yaml
load_yaml_directory = _common.load_yaml_directory
metadata = lambda: _common.metadata(_workspace)
validate_payload = lambda payload, schema_name: _common.validate_payload(
    _workspace, payload, schema_name
)
atomic_write_yaml = _common.atomic_write_yaml
atomic_write_json = _common.atomic_write_json
find_work_unit = lambda work_unit_id: _common.find_work_unit(_workspace, work_unit_id)
relates_to_work_unit = _common.relates_to_work_unit
observation_summary = _common.observation_summary

__all__ = [
    "ROOT",
    "AI",
    "now_utc",
    "now_iso",
    "generated_id",
    "load_yaml",
    "load_yaml_directory",
    "metadata",
    "validate_payload",
    "atomic_write_yaml",
    "atomic_write_json",
    "find_work_unit",
    "relates_to_work_unit",
    "observation_summary",
]
