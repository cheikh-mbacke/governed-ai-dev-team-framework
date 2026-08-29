"""Update and dry-run tests (Document 14 DI-002, DI-004, DI-011)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from distribution.installer.record import INSTALLATION_RECORD_FILE

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"


def _install(target: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "update-test",
            "--project-name",
            "Update Test",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _git_init(target: Path) -> None:
    commands = [
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Distribution Test"],
        ["git", "config", "user.email", "distribution-test@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=target, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr + result.stdout


def test_di002_dry_run_makes_no_changes(tmp_path: Path) -> None:
    target = tmp_path / "project"
    _install(target)
    _git_init(target)
    cli_path = target / ".cursor" / "cli.json"
    before = cli_path.read_bytes()
    record_before = (target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--update",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DRY-RUN: no file was modified" in proc.stdout
    assert cli_path.read_bytes() == before
    assert (target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8") == record_before


def test_di004_project_owned_profile_preserved_on_update(tmp_path: Path) -> None:
    target = tmp_path / "project"
    _install(target)
    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["extensions"] = {"user_marker": "keep-me"}
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    before = profile_path.read_bytes()
    _git_init(target)

    proc = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--update",
            "--skip-validation",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert profile_path.read_bytes() == before
    updated = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert updated["extensions"]["user_marker"] == "keep-me"


def test_di011_dirty_git_refused_without_override(tmp_path: Path) -> None:
    target = tmp_path / "project"
    _install(target)
    _git_init(target)
    cli_path = target / ".cursor" / "cli.json"
    original = cli_path.read_text(encoding="utf-8")
    cli_path.write_text(original + "\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(INSTALL), "--target", str(target), "--update"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 2
    assert "dirty" in proc.stdout.lower() or "aborted" in proc.stdout.lower()
    assert cli_path.read_text(encoding="utf-8") == original + "\n"


def test_di009_incompatible_version_refused(tmp_path: Path) -> None:
    target = tmp_path / "project"
    _install(target)
    record_path = target / INSTALLATION_RECORD_FILE
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["core"]["version"] = "9.9.9"
    record["adapters"][0]["version"] = "9.9.9"
    record["distribution"]["version"] = "9.9.9"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    _git_init(target)

    proc = subprocess.run(
        [sys.executable, str(INSTALL), "--target", str(target), "--update"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 2
    assert "9.9.9" in proc.stdout or "migration path" in proc.stdout.lower()
