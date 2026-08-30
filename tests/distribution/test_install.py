"""Fresh install tests (Document 14 DI-001)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from distribution.installer.record import INSTALLATION_RECORD_FILE, is_installation_record

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"


def _run_install(target: Path, project_id: str = "di001-test") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            project_id,
            "--project-name",
            "DI-001 Test",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def test_di001_fresh_install_writes_v2_record_last(tmp_path: Path) -> None:
    target = tmp_path / "fresh"
    before = subprocess.run(
        [sys.executable, str(INSTALL), "--target", str(target), "--project-id", "x"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert before.returncode != 0

    result = _run_install(target)
    assert result.returncode == 0, result.stdout + result.stderr

    record_path = target / INSTALLATION_RECORD_FILE
    assert record_path.is_file()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert is_installation_record(record)
    assert record["schema_version"] == 3
    assert record["active_adapter_id"] == "cursor"
    assert record["core"]["version"]
    assert record["adapters"][0]["id"] == "cursor"
    distribution_paths = record["distribution"]["managed_files"]
    distribution_path_strings = [
        entry if isinstance(entry, str) else entry["path"] for entry in distribution_paths
    ]
    assert INSTALLATION_RECORD_FILE.as_posix() in distribution_path_strings

    profile = yaml.safe_load((target / ".ai-team/project-profile.yaml").read_text(encoding="utf-8"))
    assert profile.get("active_adapter_id") == "cursor"
    assert profile["project"]["id"] == "di001-test"

    mtime_record = record_path.stat().st_mtime
    legacy = target / ".ai-team/framework-version.json"
    assert legacy.is_file()
    assert record_path.stat().st_mtime >= legacy.stat().st_mtime or abs(mtime_record - legacy.stat().st_mtime) < 2
