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


def _ensure_adapters_cursor_alias(repo: Path) -> None:
    """Map ``adapters.cursor`` onto the installed runtime copy when needed.

    Fresh installs place the Cursor adapter under
    ``.ai-team/runtime/governed_ai/adapters/cursor/`` and do not ship a
    top-level ``adapters/`` package. SPI modules still import
    ``adapters.cursor.*``; aliasing keeps those imports working without
    requiring the framework-source layout.
    """
    if (repo / "adapters" / "cursor").is_dir():
        return
    if "adapters.cursor" in sys.modules:
        return
    try:
        importlib.import_module("adapters.cursor")
        return
    except ModuleNotFoundError:
        pass
    try:
        ga_cursor = importlib.import_module("governed_ai.adapters.cursor")
    except ModuleNotFoundError:
        return

    adapters_mod = sys.modules.get("adapters")
    if adapters_mod is None:
        adapters_mod = types.ModuleType("adapters")
        adapters_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["adapters"] = adapters_mod
    sys.modules["adapters.cursor"] = ga_cursor
    setattr(adapters_mod, "cursor", ga_cursor)


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

    _ensure_adapters_cursor_alias(repo)
    return repo


def import_adapters_cursor(dotted: str):
    """Import ``adapters.cursor.<dotted>`` with installed-layout fallback."""
    try:
        return importlib.import_module(f"adapters.cursor.{dotted}")
    except ModuleNotFoundError:
        return importlib.import_module(f"governed_ai.adapters.cursor.{dotted}")
