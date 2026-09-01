"""Release compatibility matrix tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.errors import InstallationValidationError
from distribution.installer.version_policy import (
    RELEASE_MATRIX,
    validate_adapter_descriptor_alignment,
    validate_release_matrix,
    validate_update_path,
)


def test_release_matrix_declares_current_product_version() -> None:
    assert "0.7.0" in RELEASE_MATRIX


def test_validate_update_path_rejects_downgrade() -> None:
    with pytest.raises(InstallationValidationError) as exc:
        validate_update_path("0.7.0", "0.6.0")
    assert exc.value.code == "DOWNGRADE_NOT_SUPPORTED"


def test_validate_update_path_allows_idempotent_reinstall() -> None:
    validate_update_path("0.7.0", "0.7.0")


def test_validate_update_path_rejects_unknown_target() -> None:
    with pytest.raises(InstallationValidationError) as exc:
        validate_update_path("0.6.0", "9.9.9")
    assert exc.value.code == "UNKNOWN_RELEASE"


def test_adapter_descriptor_must_match_release_matrix() -> None:
    errors = validate_adapter_descriptor_alignment(
        "0.7.0",
        "cursor",
        {
            "adapter_version": "0.5.0",
            "bundle_version_range": ">=1.0.0,<2.0.0",
            "protocol_versions": ["1.0"],
        },
    )
    assert any("adapter_version" in error for error in errors)


def test_adapter_descriptor_aligned_with_matrix_has_no_errors() -> None:
    errors = validate_adapter_descriptor_alignment(
        "0.7.0",
        "cursor",
        {
            "adapter_version": "0.7.0",
            "bundle_version_range": ">=1.0.0,<2.0.0",
            "protocol_versions": ["1.0"],
        },
    )
    assert errors == []


def test_validate_release_matrix_passes_for_current_repo() -> None:
    assert validate_release_matrix(REPO_ROOT) == []


def test_validate_release_matrix_rejects_missing_entry(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    errors = validate_release_matrix(tmp_path)
    assert any("RELEASE_MATRIX" in error for error in errors)


def test_check_release_matrix_cli_success() -> None:
    import subprocess

    proc = subprocess.run(
        [sys.executable, "scripts/ai-team/check_release_matrix.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout
