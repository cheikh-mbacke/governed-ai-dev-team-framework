from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from governed_ai.core.orchestrator.git_workspace import (
    GitWorkspaceError,
    ensure_integration_worktree,
    ensure_work_unit_worktree,
    merge_and_revalidate,
)


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root}", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def _repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "l4@example.test")
    _git(tmp_path, "config", "user.name", "L4 Test")
    (tmp_path / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "shared.txt")
    _git(tmp_path, "commit", "-m", "test: base")
    return tmp_path


def test_real_worktree_merge_and_full_revalidation(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    worker = ensure_work_unit_worktree(root, "RUN-L4-GIT", "WU-A")
    (worker / "feature.txt").write_text("implemented\n", encoding="utf-8")
    _git(worker, "add", "feature.txt")
    _git(worker, "commit", "-m", "feat(WU-A): implementation")

    merge_sha, evidence = merge_and_revalidate(
        root,
        run_id="RUN-L4-GIT",
        work_unit_id="WU-A",
        integration_branch="integration/RUN-L4-GIT",
        verification_command="git status --porcelain",
    )
    assert len(merge_sha) == 40
    assert evidence.startswith("sha256:")
    integration = ensure_integration_worktree(root, "RUN-L4-GIT", "integration/RUN-L4-GIT")
    assert (integration / "feature.txt").read_text(encoding="utf-8") == "implemented\n"


def test_real_merge_conflict_is_detected_and_aborted(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    worker = ensure_work_unit_worktree(root, "RUN-L4-CONFLICT", "WU-A")
    (worker / "shared.txt").write_text("worker\n", encoding="utf-8")
    _git(worker, "add", "shared.txt")
    _git(worker, "commit", "-m", "feat(WU-A): worker change")

    integration = ensure_integration_worktree(
        root, "RUN-L4-CONFLICT", "integration/RUN-L4-CONFLICT"
    )
    (integration / "shared.txt").write_text("integration\n", encoding="utf-8")
    _git(integration, "add", "shared.txt")
    _git(integration, "commit", "-m", "test: integration change")

    with pytest.raises(GitWorkspaceError, match="integration conflict"):
        merge_and_revalidate(
            root,
            run_id="RUN-L4-CONFLICT",
            work_unit_id="WU-A",
            integration_branch="integration/RUN-L4-CONFLICT",
            verification_command="git status --porcelain",
        )
    merge_head = subprocess.run(
        ["git", "-c", f"safe.directory={integration}", "rev-parse", "--verify", "MERGE_HEAD"],
        cwd=integration,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert merge_head.returncode != 0
