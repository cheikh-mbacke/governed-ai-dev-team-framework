"""Governed evidence must be committable when the product gitignore ignores *.log."""

from __future__ import annotations

import subprocess
from pathlib import Path

from governed_ai.core.execution_gateway.transactional import create_governed_commit


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_force_adds_ignored_evidence_log(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "governed-ai@local")
    _git(tmp_path, "config", "user.name", "Governed AI")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("product\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md", ".gitignore")
    _git(tmp_path, "commit", "-m", "init")

    evidence = tmp_path / ".ai-team" / "evidence" / "WU-A"
    evidence.mkdir(parents=True)
    log = evidence / "verify-run.log"
    log.write_text("checks passed\n", encoding="utf-8")

    create_governed_commit(
        tmp_path,
        work_unit_id="WU-A",
        execution_id="EXE-1",
        paths=[".ai-team/evidence/WU-A/verify-run.log"],
    )
    tracked = subprocess.run(
        ["git", "ls-files", ".ai-team/evidence/WU-A/verify-run.log"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout.strip().endswith("verify-run.log")
