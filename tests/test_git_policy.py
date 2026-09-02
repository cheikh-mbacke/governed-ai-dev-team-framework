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


def _write_client_profile(root: Path) -> None:
    (root / ".ai-team").mkdir(parents=True, exist_ok=True)
    (root / ".ai-team" / "project-profile.yaml").write_text(
        "project:\n  repository_kind: existing_or_greenfield_project\n",
        encoding="utf-8",
    )


def test_fabrication_branch_names_on_source_repo() -> None:
    valid = ["main", "renov/framework-source-mode", "fix/ci", "feat/api", "docs/readme"]
    invalid = ["wu/WU-GIT-GOVERNANCE", "random-branch", "mode-nuit"]
    assert all(POLICY.branch_is_valid(branch, ROOT) for branch in valid)
    assert not any(POLICY.branch_is_valid(branch, ROOT) for branch in invalid)


def test_client_branch_names() -> None:
    valid = [
        "main",
        "wu/WU-GIT-GOVERNANCE",
        "ai-run/RUN-42/WU-TEST",
        "integration/RUN-42",
        "hotfix/WU-SEC-42",
        "release/0.7",
    ]
    invalid = ["master", "feat/free-form", "mode-nuit", "release/0.7.0", "wu/no-id"]
    client_root = ROOT / "tests" / "_git_policy_client_fixture"
    # Use an isolated path under tests/ only if needed; tmp_path is cleaner.
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        client_root = Path(temp_dir)
        _write_client_profile(client_root)
        assert all(POLICY.branch_is_valid(branch, client_root) for branch in valid)
        assert not any(POLICY.branch_is_valid(branch, client_root) for branch in invalid)


def test_fabrication_commit_subjects_on_source_repo() -> None:
    assert POLICY.commit_subject_is_valid("feat: ajouter la garde fabrication", ROOT)
    assert POLICY.commit_subject_is_valid("fix!: rupture de compatibilite", ROOT)
    assert not POLICY.commit_subject_is_valid("feat(WU-API-42): ajouter le contrat", ROOT)


def test_client_commit_subjects() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        client_root = Path(temp_dir)
        _write_client_profile(client_root)
        assert POLICY.commit_subject_is_valid(
            "feat(WU-API-42): ajouter le contrat", client_root
        )
        assert POLICY.commit_subject_is_valid(
            "fix(WU-API-42)!: retirer le format historique", client_root
        )
        assert POLICY.commit_subject_is_valid(
            "wip(WU-API-42): conserver le point de reprise", client_root
        )
        assert not POLICY.commit_subject_is_valid("feat(api): ajouter le contrat", client_root)
        assert not POLICY.commit_subject_is_valid("chore: changement sans Work Unit", client_root)


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


def test_client_repo_without_pyproject_toml_is_not_a_version_error(tmp_path: Path) -> None:
    # canonical_version_source: pyproject.toml is the framework's own convention
    # (see distribution/payload/.ai-team/constitution/95-git-release-policy.yaml,
    # which itself notes "adapt: package.json, VERSION, setup.cfg, etc."). An
    # installed client project must not be forced to have a pyproject.toml.
    _write_client_profile(tmp_path)
    assert POLICY.validate_versions(tmp_path) == []


def test_changelog_release_section_requires_iso_date() -> None:
    changelog = "## [0.7.1] - 2026-09-01\n\nInitial note.\n"
    assert POLICY.validate_changelog_release_section("0.7.1", changelog) == []


def test_changelog_release_section_rejects_placeholder_date() -> None:
    changelog = "## [0.7.0] - Non publiée\n\nNot ready.\n"
    errors = POLICY.validate_changelog_release_section("0.7.0", changelog)
    assert any("not publish-ready" in error for error in errors)


def test_changelog_release_section_requires_header() -> None:
    errors = POLICY.validate_changelog_release_section("0.8.0", "## [Unreleased]\n")
    assert any("must declare" in error for error in errors)


def test_tag_payload_declares_signature() -> None:
    unsigned = "object abc\ntype commit\n..."
    signed = "object abc\ntype tag\ngpgsig -----BEGIN PGP SIGNATURE-----\n"
    assert not POLICY.tag_payload_declares_signature(unsigned)
    assert POLICY.tag_payload_declares_signature(signed)
