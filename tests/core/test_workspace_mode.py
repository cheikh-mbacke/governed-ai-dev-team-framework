"""Tests for framework_source workspace guards."""

from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import (
    collect_framework_source_client_cycle_artifacts,
    collect_framework_source_root_layout_violations,
    is_framework_source,
    read_repository_kind,
)
from governed_ai.core.fabrication_overlay import (
    collect_framework_source_fabrication_overlay_violations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_AI_TEAM = REPO_ROOT / "distribution" / "payload" / ".ai-team"
SEED_STATE = REPO_ROOT / "distribution" / "payload" / "seeds" / "project-state.yaml"


def test_read_repository_kind_on_source_repo() -> None:
    assert read_repository_kind(REPO_ROOT) == "framework_source"


def test_is_framework_source_on_source_repo() -> None:
    assert is_framework_source(Workspace.from_root(REPO_ROOT))


def test_no_root_ai_team_directory() -> None:
    assert collect_framework_source_root_layout_violations(REPO_ROOT) == []
    assert not (REPO_ROOT / ".ai-team").exists()


def test_workspace_ai_team_points_at_payload_depot() -> None:
    workspace = Workspace.from_root(REPO_ROOT)
    assert workspace.ai_team == PAYLOAD_AI_TEAM


def test_seed_project_state_is_virgin() -> None:
    import yaml

    state = yaml.safe_load(SEED_STATE.read_text(encoding="utf-8"))
    assert state["phase"] == "not_compiled"
    assert state["work_units"] == {}


def test_no_client_cycle_artifacts_on_source_repo() -> None:
    import yaml

    state = yaml.safe_load(SEED_STATE.read_text(encoding="utf-8"))
    assert collect_framework_source_client_cycle_artifacts(PAYLOAD_AI_TEAM, state=state) == []


def test_fabrication_cursor_overlay_is_minimal() -> None:
    assert collect_framework_source_fabrication_overlay_violations(REPO_ROOT) == []


def test_feedback_record_blocked_on_framework_source() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ai-team/feedback.py",
            "record",
            "--category",
            "tooling",
            "--symptom",
            "should be blocked on framework_source",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "framework_source" in (result.stderr + result.stdout).lower()


def test_validate_passes_on_source_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ai-team/validate.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_gov_command_blocked_on_framework_source() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ai-team/gov.py",
            "query",
            "project-state",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "framework_source" in (result.stderr + result.stdout).lower()


def test_orchestrate_blocked_on_framework_source() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ai-team/orchestrate.py",
            "--run-id",
            "RUN-NOPE",
            "--max-ticks",
            "1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "framework_source" in (result.stderr + result.stdout).lower()


def test_diagnose_fabrication_mode() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ai-team/diagnose.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "framework_source" in (result.stderr + result.stdout).lower()
    assert "work units" not in result.stdout.lower()


def test_gov_validate_notes_fabrication_mode() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ai-team/gov.py", "validate"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload.get("workspace_mode") == "framework_source"
    assert "fabrication" in payload.get("note", "").lower()
