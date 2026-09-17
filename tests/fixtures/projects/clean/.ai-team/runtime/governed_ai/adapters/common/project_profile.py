"""Minimal Project Profile shape shared by every Adaptateur's install-time compiler.

Extracted from ``adapters/cursor/compiler/install_support.py`` — no
Cursor-specific content.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


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


__all__ = ["load_project_profile_yaml", "minimal_project_profile"]
