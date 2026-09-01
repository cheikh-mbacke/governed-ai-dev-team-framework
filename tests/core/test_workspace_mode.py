"""Tests for framework_source workspace guards."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import (
    collect_framework_source_client_cycle_artifacts,
    is_framework_source,
    read_repository_kind,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_read_repository_kind_on_source_repo() -> None:
    assert read_repository_kind(REPO_ROOT) == "framework_source"


def test_is_framework_source_on_source_repo() -> None:
    assert is_framework_source(Workspace.from_root(REPO_ROOT))


def test_project_state_is_virgin() -> None:
    import yaml

    state = yaml.safe_load(
        (REPO_ROOT / ".ai-team" / "state" / "project-state.yaml").read_text(encoding="utf-8")
    )
    assert state["phase"] == "not_compiled"
    assert state["work_units"] == {}


def test_no_client_cycle_artifacts_on_source_repo() -> None:
    import yaml

    state = yaml.safe_load(
        (REPO_ROOT / ".ai-team" / "state" / "project-state.yaml").read_text(encoding="utf-8")
    )
    assert collect_framework_source_client_cycle_artifacts(REPO_ROOT / ".ai-team", state=state) == []


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
