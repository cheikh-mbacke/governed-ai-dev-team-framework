"""Shared helpers for core tests that simulate installed client workspaces."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.feedback.submit import CURRENT_TERMS_VERSION

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
    telemetry_collection: str | None = None,
) -> None:
    source_profile = SEED_PROFILE
    profile = yaml.safe_load(source_profile.read_text(encoding="utf-8")) or {}
    project = profile.setdefault("project", {})
    project["id"] = project_id
    project["repository_kind"] = "existing_or_greenfield_project"
    profile.setdefault("setup_status", {})["template"] = False
    telemetry = profile.setdefault("telemetry", {})
    if telemetry_collection is not None:
        telemetry["collection"] = telemetry_collection
    elif "collection" not in telemetry:
        telemetry["collection"] = "consented_share"
    if not telemetry.get("project_ref"):
        telemetry["project_ref"] = "PRJ-" + ("a" * 32)
    # Simulate installer acceptance under consented_share (ADR-009).
    if telemetry.get("collection") != "disabled":
        telemetry.setdefault("terms_version", CURRENT_TERMS_VERSION)
        if not telemetry.get("terms_accepted_at"):
            telemetry["terms_accepted_at"] = datetime.now(UTC).isoformat()
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def attach_minimal_out_of_tree_ensemble(
    instance_root: Path,
    *,
    ensemble_id: str = "test-ensemble",
    member_id: str = "app",
) -> Path:
    """Declare one out-of-tree member so product Command Gateway cycles are allowed.

    Ensemble registration commands remain testable on bare instances; call this
    helper from fixtures that exercise CreateWorkUnit, gates, runs, etc.
    """
    member = instance_root.parent / f"{instance_root.name}-member"
    if not (member / ".git").exists():
        member.mkdir(parents=True, exist_ok=True)
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.name", "Test Member"],
            ["git", "config", "user.email", "member@example.invalid"],
        ):
            completed = subprocess.run(command, cwd=member, capture_output=True, text=True)
            assert completed.returncode == 0, completed.stderr
        (member / "README").write_text("member\n", encoding="utf-8")
        for command in (
            ["git", "add", "README"],
            ["git", "commit", "-qm", "fixture"],
        ):
            completed = subprocess.run(command, cwd=member, capture_output=True, text=True)
            assert completed.returncode == 0, completed.stderr

    ai_team = instance_root / ".ai-team"
    ai_team.mkdir(parents=True, exist_ok=True)
    (ai_team / "active-ensemble.yaml").write_text(
        f"ensemble_id: {ensemble_id}\n",
        encoding="utf-8",
    )
    ensemble_dir = ai_team / "ensembles" / ensemble_id
    ensemble_dir.mkdir(parents=True, exist_ok=True)
    rel = Path(os_path_rel(member, instance_root)).as_posix()
    (ensemble_dir / "members.yaml").write_text(
        yaml.safe_dump(
            {
                "ensemble_id": ensemble_id,
                "revision": 1,
                "members": [
                    {
                        "id": member_id,
                        "kind": "service",
                        "path": rel,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return member


def os_path_rel(target: Path, start: Path) -> str:
    import os

    return os.path.relpath(target, start)
