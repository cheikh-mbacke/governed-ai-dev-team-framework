"""Tests for the executable Git and release policy."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "ai-team" / "check_git_policy.py"
SPEC = importlib.util.spec_from_file_location("check_git_policy", MODULE_PATH)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def test_governed_branch_names() -> None:
    valid = [
        "main",
        "wu/WU-GIT-GOVERNANCE",
        "ai-run/RUN-42/WU-TEST",
        "integration/RUN-42",
        "hotfix/WU-SEC-42",
        "release/0.7",
    ]
    invalid = ["master", "feat/free-form", "mode-nuit", "release/0.7.0", "wu/no-id"]
    assert all(POLICY.branch_is_valid(branch) for branch in valid)
    assert not any(POLICY.branch_is_valid(branch) for branch in invalid)


def test_governed_commit_subjects() -> None:
    assert POLICY.commit_subject_is_valid("feat(WU-API-42): ajouter le contrat")
    assert POLICY.commit_subject_is_valid("fix(WU-API-42)!: retirer le format historique")
    assert POLICY.commit_subject_is_valid("wip(WU-API-42): conserver le point de reprise")
    assert not POLICY.commit_subject_is_valid("feat(api): ajouter le contrat")
    assert not POLICY.commit_subject_is_valid("chore: changement sans Work Unit")


def _write_version_sources(root: Path, pyproject: str, framework: str) -> None:
    (root / ".ai-team").mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "example"\nversion = "{pyproject}"\n', encoding="utf-8"
    )
    (root / ".ai-team" / "framework-version.json").write_text(
        json.dumps({"version": framework}), encoding="utf-8"
    )


def test_product_versions_must_match_and_use_semver(tmp_path: Path) -> None:
    _write_version_sources(tmp_path, "0.7.0", "0.7.0")
    assert POLICY.validate_versions(tmp_path) == []

    (tmp_path / ".ai-team" / "framework-version.json").write_text(
        json.dumps({"version": "0.7.1"}), encoding="utf-8"
    )
    errors = POLICY.validate_versions(tmp_path)
    assert any("mismatch" in error for error in errors)


def test_non_semver_product_version_is_rejected(tmp_path: Path) -> None:
    _write_version_sources(tmp_path, "release-7", "release-7")
    errors = POLICY.validate_versions(tmp_path)
    assert len(errors) >= 2
    assert any("not SemVer" in error for error in errors)
