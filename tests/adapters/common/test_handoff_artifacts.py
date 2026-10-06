"""Handoff artifact sanitizer — build outputs, host paths, evidence names."""

from __future__ import annotations

from pathlib import Path

from governed_ai.adapters.common.handoff_artifacts import sanitize_handoff
from governed_ai.core.execution_gateway.evidence import sha256_file


def test_sanitize_drops_packages_and_relocates_host_evidence(tmp_path: Path) -> None:
    host_log = tmp_path / "outside" / "verify-run.log"
    host_log.parent.mkdir()
    host_log.write_text("checks passed\n", encoding="utf-8")
    project = tmp_path / "repo"
    project.mkdir()
    package = project / "target" / "app.jar"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"not-a-real-package")
    loose_wheel = project / "dist-cache" / "lib.whl"
    loose_wheel.parent.mkdir(parents=True)
    loose_wheel.write_bytes(b"wheel")

    artifacts, checks = sanitize_handoff(
        project,
        "WU-A",
        artifacts=[
            {"kind": "file", "path": "target/app.jar", "sha256": "sha256:" + "ab" * 32},
            {"kind": "file", "path": "dist-cache/lib.whl", "sha256": "sha256:" + "11" * 32},
            {"kind": "file", "path": str(host_log), "sha256": "sha256:" + "cd" * 32},
            {"kind": "file", "path": "/tmp/missing.log", "sha256": "sha256:" + "ef" * 32},
        ],
        checks=[{"name": "tests", "status": "passed", "evidence_ref": str(host_log)}],
    )

    assert [item["path"] for item in artifacts] == [
        ".ai-team/evidence/WU-A/verify-run.txt"
    ]
    relocated = project / artifacts[0]["path"]
    assert relocated.is_file()
    assert artifacts[0]["sha256"] == sha256_file(relocated)
    assert artifacts[0]["agent_reported_sha256"] == artifacts[0]["sha256"]
    assert checks[0]["evidence_ref"] == artifacts[0]["path"]


def test_sanitize_renames_gitignore_log_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / ".ai-team" / "evidence" / "WU-A"
    evidence.mkdir(parents=True)
    log = evidence / "verify-run.log"
    log.write_text("ok\n", encoding="utf-8")
    artifacts, _checks = sanitize_handoff(
        tmp_path,
        "WU-A",
        artifacts=[
            {
                "kind": "file",
                "path": ".ai-team/evidence/WU-A/verify-run.log",
                "sha256": "sha256:" + "11" * 32,
            }
        ],
        checks=[],
    )
    assert artifacts[0]["path"] == ".ai-team/evidence/WU-A/verify-run.txt"
    assert not log.exists()
    assert (tmp_path / artifacts[0]["path"]).is_file()
