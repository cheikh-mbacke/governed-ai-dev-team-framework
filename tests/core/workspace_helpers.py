"""Shared helpers for core tests that simulate installed client workspaces."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_installed_client_profile(
    ai_team: Path,
    *,
    project_id: str = "test-project",
) -> None:
    source_profile = REPO_ROOT / ".ai-team" / "project-profile.yaml"
    profile = yaml.safe_load(source_profile.read_text(encoding="utf-8")) or {}
    project = profile.setdefault("project", {})
    project["id"] = project_id
    project["repository_kind"] = "existing_or_greenfield_project"
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
