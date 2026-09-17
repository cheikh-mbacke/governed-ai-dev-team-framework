"""Resolve framework runtime import roots and requirement file paths."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


def repo_root_from_script(script_file: str | Path) -> Path:
    return Path(script_file).resolve().parents[2]


def requirements_file(root: Path) -> Path:
    ai_team = root / ".ai-team" / "requirements.txt"
    if ai_team.is_file():
        return ai_team
    return root / "requirements.txt"


def requirements_install_hint(root: Path) -> str:
    return f"pip install -r {requirements_file(root).relative_to(root).as_posix()}"


def _ensure_adapter_alias(repo: Path, adapter_dir_name: str) -> None:
    """Map ``adapters.<adapter_dir_name>`` onto the installed runtime copy when needed.

    Fresh installs place the active Adaptateur under
    ``.ai-team/runtime/governed_ai/adapters/<adapter_dir_name>/`` and do not
    ship a top-level ``adapters/`` package. SPI modules still import
    ``adapters.<adapter_dir_name>.*``; aliasing keeps those imports working
    without requiring the framework-source layout. Generalized from the
    original Cursor-only ``_ensure_adapters_cursor_alias`` — nothing about
    this mechanism is Cursor-specific, only its previous hardcoded name.
    """
    dotted = f"adapters.{adapter_dir_name}"
    if (repo / "adapters" / adapter_dir_name).is_dir():
        return
    if dotted in sys.modules:
        return
    try:
        importlib.import_module(dotted)
        return
    except ModuleNotFoundError:
        pass
    try:
        ga_module = importlib.import_module(f"governed_ai.adapters.{adapter_dir_name}")
    except ModuleNotFoundError:
        return

    adapters_mod = sys.modules.get("adapters")
    if adapters_mod is None:
        adapters_mod = types.ModuleType("adapters")
        adapters_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["adapters"] = adapters_mod
    sys.modules[dotted] = ga_module
    setattr(adapters_mod, adapter_dir_name, ga_module)


def _ensure_adapters_cursor_alias(repo: Path) -> None:
    """Backward-compatible name — see _ensure_adapter_alias."""
    _ensure_adapter_alias(repo, "cursor")


def bootstrap_runtime(root: Path | None = None) -> Path:
    """Configure sys.path for governed_ai and adapters imports. Returns repo root."""
    repo = (root or Path.cwd()).resolve()
    runtime_parent = repo / ".ai-team" / "runtime"
    runtime_pkg = runtime_parent / "governed_ai"
    legacy_src = repo / "src"

    if runtime_pkg.is_dir():
        if str(runtime_parent) not in sys.path:
            sys.path.insert(0, str(runtime_parent))
    elif (legacy_src / "governed_ai").is_dir():
        if str(legacy_src) not in sys.path:
            sys.path.insert(0, str(legacy_src))

    if (repo / "adapters").is_dir() and str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    elif runtime_pkg.is_dir() and str(runtime_parent) not in sys.path:
        sys.path.insert(0, str(runtime_parent))

    _ensure_adapter_alias(repo, "cursor")
    _ensure_adapter_alias(repo, "claude_code")
    return repo


def import_adapters_cursor(dotted: str):
    """Import ``adapters.cursor.<dotted>`` with installed-layout fallback."""
    return import_adapter_module("cursor", dotted)


def import_adapter_module(adapter_dir_name: str, dotted: str):
    """Import ``adapters.<adapter_dir_name>.<dotted>`` with installed-layout fallback."""
    try:
        return importlib.import_module(f"adapters.{adapter_dir_name}.{dotted}")
    except ModuleNotFoundError:
        return importlib.import_module(f"governed_ai.adapters.{adapter_dir_name}.{dotted}")
