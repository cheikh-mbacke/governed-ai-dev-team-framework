"""Re-export compiler entry point from the adapter tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.cursor.compiler.compile import compile_manifest as _compile_manifest


def compile_manifest(
    bundle_dir: Path,
    staging_dir: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    templates_root: Path | None = None,
) -> dict[str, Any]:
    return _compile_manifest(
        bundle_dir,
        staging_dir,
        project_profile,
        templates_root=templates_root,
    )


__all__ = ["compile_manifest"]
