"""Build framework-version.json for the framework source/distribution repository.

The source repo layout (``src/governed_ai/``, ``adapters/cursor/``, …) differs
from an installed target (``.ai-team/runtime/governed_ai/``, …). This module
derives the install payload as **source-relative** paths, never installed-target
paths.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from distribution.installer.fabrication_layout import profile_path, source_version_file
from distribution.installer.source_files import build_copy_plan


def read_product_version(source_root: Path) -> str:
    text = (source_root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']\s*$', text)
    if not match:
        raise ValueError("pyproject.toml does not declare project.version")
    return match.group(1)


def build_source_managed_files(
    source_root: Path,
    *,
    project_id: str | None = None,
) -> list[str]:
    """Return sorted source-relative paths that constitute the install payload."""
    source_root = source_root.resolve()
    profile_src = profile_path(source_root)
    if profile_src is None or not profile_src.is_file():
        raise FileNotFoundError("Missing fabrication or client project-profile.yaml")

    with tempfile.TemporaryDirectory(prefix="source-manifest-") as tmp:
        target = Path(tmp) / "manifest-target"
        target.mkdir()
        dest_profile = target / ".ai-team" / "project-profile.yaml"
        dest_profile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile_src, dest_profile)

        resolved_project_id = project_id
        if resolved_project_id is None:
            import yaml

            profile = yaml.safe_load(profile_src.read_text(encoding="utf-8")) or {}
            resolved_project_id = (profile.get("project") or {}).get("id") or "framework-renov"

        source_paths: set[str] = set()
        entries, _managed = build_copy_plan(
            source_root,
            target,
            project_id=resolved_project_id,
            compile_cursor=True,
        )
        for entry in entries:
            try:
                source_rel = entry.source.relative_to(source_root).as_posix()
            except ValueError:
                # Compiled Cursor artifacts live in temporary staging. Their
                # editable provenance is already covered by the compiler,
                # bundle, and adapters/cursor/templates sources enumerated by
                # the copy plan. Never reinterpret a compiled destination as a
                # root source path: root .cursor/ is fabrication-only.
                continue
            if (source_root / source_rel).is_file():
                source_paths.add(source_rel)

    return sorted(source_paths)


def build_source_manifest(source_root: Path, *, version: str | None = None) -> dict:
    source_root = source_root.resolve()
    resolved_version = version or read_product_version(source_root)
    return {
        "schema_version": 1,
        "version": resolved_version,
        "managed_files": build_source_managed_files(source_root),
    }


def write_source_manifest(
    source_root: Path,
    *,
    version: str | None = None,
) -> Path:
    source_root = source_root.resolve()
    payload = build_source_manifest(source_root, version=version)
    path = source_version_file(source_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


__all__ = [
    "build_source_managed_files",
    "build_source_manifest",
    "read_product_version",
    "write_source_manifest",
]
