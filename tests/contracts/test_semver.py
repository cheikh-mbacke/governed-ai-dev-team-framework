"""SemVer helper tests."""

from __future__ import annotations

import pytest

from governed_ai.contracts.semver import compare_semver, parse_semver, version_in_range


def test_parse_semver_accepts_prerelease() -> None:
    parsed = parse_semver("1.2.3-alpha.1")
    assert parsed.major == 1
    assert parsed.prerelease == ("alpha", "1")


def test_compare_semver_orders_patch_levels() -> None:
    assert compare_semver("0.9.0", "0.10.0") < 0
    assert compare_semver("0.10.0", "0.9.0") > 0


def test_compare_semver_prerelease_before_release() -> None:
    assert compare_semver("1.0.0-alpha", "1.0.0") < 0


def test_version_in_range_respects_upper_bound() -> None:
    assert version_in_range("1.0.0", ">=1.0.0,<2.0.0")
    assert not version_in_range("2.0.0", ">=1.0.0,<2.0.0")
    assert version_in_range("1.9.9", ">=1.0.0,<2.0.0")


def test_version_in_range_rejects_invalid_spec() -> None:
    with pytest.raises(ValueError):
        version_in_range("1.0.0", "1.0.0")
