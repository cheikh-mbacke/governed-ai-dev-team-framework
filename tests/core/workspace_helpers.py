"""Shared helpers for core tests that simulate installed client workspaces."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_AI_TEAM = REPO_ROOT / "distribution" / "payload" / ".ai-team"
FABRIC_ROOT = REPO_ROOT / ".fabric"
SEED_PROFILE = REPO_ROOT / "distribution" / "payload" / "seeds" / "project-profile.yaml"


def repo_payload_ai_team() -> Path:
    return PAYLOAD_AI_TEAM


def write_installed_client_profile(
    ai_team: Path,
    *,
    project_id: str = "test-project",
) -> None:
    source_profile = SEED_PROFILE
    profile = yaml.safe_load(source_profile.read_text(encoding="utf-8")) or {}
    project = profile.setdefault("project", {})
    project["id"] = project_id
    project["repository_kind"] = "existing_or_greenfield_project"
    profile.setdefault("setup_status", {})["template"] = False
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
