from __future__ import annotations

import pytest

from governed_ai.core.code_revision import normalize_code_revision


def test_normalize_standalone_string() -> None:
    assert normalize_code_revision("abc123") == {"kind": "git_commit", "sha": "abc123"}


def test_normalize_null() -> None:
    assert normalize_code_revision(None) is None


def test_normalize_git_commit_object() -> None:
    assert normalize_code_revision(
        {"kind": "git_commit", "sha": "abc", "member_id": "backend"}
    ) == {"kind": "git_commit", "sha": "abc", "member_id": "backend"}


def test_normalize_composition_object() -> None:
    payload = {
        "kind": "composition",
        "composition_id": "CR-1",
        "members": {"backend": "a" * 40},
    }
    assert normalize_code_revision(payload)["composition_id"] == "CR-1"


def test_normalize_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        normalize_code_revision("  ")
