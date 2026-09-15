"""Install-time Claude Code compilation (Distribution bridge until WU-P5).

Mirrors ``adapters/cursor/compiler/install_support.py``.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from governed_ai.adapters.common.bundle import resolve_bundle_dir
from governed_ai.adapters.common.project_profile import (
    load_project_profile_yaml,
    minimal_project_profile,
)

from .compile import compile_manifest


def _ensure_import_paths(source_root: Path, target: Path | None = None) -> None:
    from distribution.installer.paths import (
        adapter_compiler_import_root,
        is_installed_runtime_layout,
    )

    root = source_root.resolve()
    import_root = adapter_compiler_import_root(root, target)
    entries = [str(root), str(import_root)]
    if not is_installed_runtime_layout(root):
        entries.append(str(root / "src"))
    for entry in entries:
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _templates_root(source_root: Path, target: Path | None = None) -> Path:
    from distribution.installer.paths import adapter_templates_root

    return adapter_templates_root(source_root, target, adapter_id="claude-code")


def compile_claude_code_tree(
    source_root: Path,
    destination_claude: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> dict[str, Any]:
    """Compile bundle + profile and copy staged ``.claude/`` to ``destination_claude``."""
    _ensure_import_paths(source_root, target)
    source_root = source_root.resolve()
    destination_claude = destination_claude.resolve()
    bundle_dir = resolve_bundle_dir(source_root, target=target)
    templates_root = _templates_root(source_root, target)
    profile = project_profile or minimal_project_profile()

    with tempfile.TemporaryDirectory(prefix="claude-code-compile-") as temp_dir:
        staging = Path(temp_dir)
        manifest = compile_manifest(
            bundle_dir,
            staging,
            profile,
            templates_root=templates_root if templates_root.is_dir() else None,
        )
        staged_claude = staging / ".claude"
        if destination_claude.exists():
            shutil.rmtree(destination_claude)
        shutil.copytree(staged_claude, destination_claude)
    return manifest


def iter_compiled_claude_code_files(
    source_root: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> Iterator[tuple[Path, Path]]:
    """Yield ``(relative_path, absolute_source_file)`` for a compiled ``.claude/`` tree."""
    _ensure_import_paths(source_root, target)
    source_root = source_root.resolve()
    bundle_dir = resolve_bundle_dir(source_root, target=target)
    templates_root = _templates_root(source_root, target)
    profile = project_profile or minimal_project_profile()

    with tempfile.TemporaryDirectory(prefix="claude-code-compile-") as temp_dir:
        staging = Path(temp_dir)
        compile_manifest(
            bundle_dir,
            staging,
            profile,
            templates_root=templates_root if templates_root.is_dir() else None,
        )
        claude_root = staging / ".claude"
        for path in sorted(claude_root.rglob("*")):
            if path.is_file():
                relative = Path(".claude") / path.relative_to(claude_root)
                yield relative, path


__all__ = [
    "compile_claude_code_tree",
    "iter_compiled_claude_code_files",
    "load_project_profile_yaml",
    "minimal_project_profile",
]
