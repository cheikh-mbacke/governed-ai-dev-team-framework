"""Tests for framework source repository manifest (not installed-target layout)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from distribution.installer.repository_kind import (
    framework_source_install_error,
    read_repository_kind,
)
from distribution.installer.source_manifest import (
    build_source_managed_files,
    read_product_version,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_VERSION = REPO_ROOT / ".fabric" / "framework-version.json"
PROJECT_PROFILE = REPO_ROOT / ".fabric" / "project-profile.yaml"
INSTALL = REPO_ROOT / "tools" / "install.py"
SYNC_MANIFEST = REPO_ROOT / "scripts" / "ai-team" / "sync_source_manifest.py"


def test_project_profile_declares_framework_source() -> None:
    profile = yaml.safe_load(PROJECT_PROFILE.read_text(encoding="utf-8"))
    assert profile["project"]["repository_kind"] == "framework_source"


def test_source_repo_has_no_installation_record() -> None:
    assert not (REPO_ROOT / ".ai-team" / "installation-record.json").exists()
    assert not (REPO_ROOT / ".ai-team").exists()


def test_framework_version_uses_source_layout_only() -> None:
    payload = json.loads(FRAMEWORK_VERSION.read_text(encoding="utf-8"))
    managed = payload["managed_files"]
    assert managed
    assert not any(path.startswith(".ai-team/runtime/") for path in managed)
    assert any(path.startswith("src/governed_ai/") for path in managed)
    assert any(path.startswith("adapters/cursor/") for path in managed)
    assert any(path.startswith("distribution/payload/.ai-team/") for path in managed)
    assert not any(path.startswith(".cursor/") for path in managed)
    for path in managed:
        assert (REPO_ROOT / path).is_file(), f"missing managed source file: {path}"


def test_framework_version_matches_pyproject() -> None:
    payload = json.loads(FRAMEWORK_VERSION.read_text(encoding="utf-8"))
    assert payload["version"] == read_product_version(REPO_ROOT)


def test_build_source_managed_files_is_deterministic() -> None:
    first = build_source_managed_files(REPO_ROOT)
    second = build_source_managed_files(REPO_ROOT)
    assert first == second
    assert first == json.loads(FRAMEWORK_VERSION.read_text(encoding="utf-8"))["managed_files"]


def test_read_repository_kind_on_source_repo() -> None:
    assert read_repository_kind(REPO_ROOT) == "framework_source"


def test_framework_source_install_error_on_self_target() -> None:
    message = framework_source_install_error(REPO_ROOT, REPO_ROOT)
    assert message is not None
    assert "framework source repository root" in message


def test_install_blocked_on_framework_source_root() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(REPO_ROOT),
            "--project-id",
            "blocked",
            "--project-name",
            "Blocked",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert "framework source repository root" in result.stdout


def test_sync_source_manifest_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SYNC_MANIFEST), "--check"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
