"""Resolve framework runtime import roots and requirement file paths."""

from __future__ import annotations

import sys
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

    return repo


def import_adapters_cursor(dotted: str):
    """Import ``adapters.cursor.<dotted>`` with installed-layout fallback."""
    from importlib import import_module

    try:
        return import_module(f"adapters.cursor.{dotted}")
    except ModuleNotFoundError:
        return import_module(f"governed_ai.adapters.cursor.{dotted}")
