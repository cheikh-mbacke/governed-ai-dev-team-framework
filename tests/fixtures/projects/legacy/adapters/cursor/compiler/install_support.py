"""Install-time Cursor compilation (Distribution bridge until WU-P5)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from adapters.cursor.compiler.compile import compile_manifest
from adapters.cursor.compiler.parity import resolve_bundle_dir


def _ensure_import_paths(source_root: Path) -> None:
    root = str(source_root.resolve())
    src = str((source_root / "src").resolve())
    for entry in (root, src):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def minimal_project_profile(
    *,
    project_id: str = "unknown",
    primary_language: str = "python",
    package_manager: str = "pip",
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "primary_language": primary_language,
        "package_manager": package_manager,
    }


def load_project_profile_yaml(profile_path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError:
        return minimal_project_profile()
    if not profile_path.is_file():
        return minimal_project_profile()
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    project = data.get("project") if isinstance(data, dict) else {}
    if not isinstance(project, dict):
        project = {}
    return minimal_project_profile(
        project_id=str(project.get("id", "unknown")),
        primary_language=str(project.get("primary_language", "python")),
        package_manager=str(project.get("package_manager", "pip")),
    )


def compile_cursor_tree(
    source_root: Path,
    destination_cursor: Path,
    project_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile bundle + profile and copy staged ``.cursor/`` to ``destination_cursor``."""
    _ensure_import_paths(source_root)
    source_root = source_root.resolve()
    destination_cursor = destination_cursor.resolve()
    bundle_dir = resolve_bundle_dir(source_root)
    templates_root = source_root / "adapters" / "cursor" / "templates"
    profile = project_profile or minimal_project_profile()

    with tempfile.TemporaryDirectory(prefix="cursor-compile-") as temp_dir:
        staging = Path(temp_dir)
        manifest = compile_manifest(
            bundle_dir,
            staging,
            profile,
            templates_root=templates_root if templates_root.is_dir() else None,
        )
        staged_cursor = staging / ".cursor"
        if destination_cursor.exists():
            shutil.rmtree(destination_cursor)
        shutil.copytree(staged_cursor, destination_cursor)
    return manifest


def iter_compiled_cursor_files(
    source_root: Path,
    project_profile: dict[str, Any] | None = None,
) -> Iterator[tuple[Path, Path]]:
    """Yield ``(relative_path, absolute_source_file)`` for a compiled ``.cursor/`` tree."""
    _ensure_import_paths(source_root)
    source_root = source_root.resolve()
    bundle_dir = resolve_bundle_dir(source_root)
    templates_root = source_root / "adapters" / "cursor" / "templates"
    profile = project_profile or minimal_project_profile()

    with tempfile.TemporaryDirectory(prefix="cursor-compile-") as temp_dir:
        staging = Path(temp_dir)
        compile_manifest(
            bundle_dir,
            staging,
            profile,
            templates_root=templates_root if templates_root.is_dir() else None,
        )
        cursor_root = staging / ".cursor"
        for path in sorted(cursor_root.rglob("*")):
            if path.is_file():
                relative = Path(".cursor") / path.relative_to(cursor_root)
                yield relative, path


__all__ = [
    "compile_cursor_tree",
    "iter_compiled_cursor_files",
    "load_project_profile_yaml",
    "minimal_project_profile",
]
