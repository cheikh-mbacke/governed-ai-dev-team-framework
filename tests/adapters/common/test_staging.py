"""governed_ai.adapters.common.staging — shared by every Adaptateur (AD-002, AD-012)."""

from __future__ import annotations

from pathlib import Path

import pytest

from governed_ai.adapters.common.staging import resolve_under_staging, sha256_bytes


def test_sha256_bytes_has_sha256_prefix() -> None:
    digest = sha256_bytes(b"hello")
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_sha256_bytes_is_deterministic() -> None:
    assert sha256_bytes(b"same content") == sha256_bytes(b"same content")
    assert sha256_bytes(b"a") != sha256_bytes(b"b")


def test_resolve_under_staging_accepts_nested_relative_path(tmp_path: Path) -> None:
    target = resolve_under_staging(tmp_path, "a/b/c.txt")
    assert target == (tmp_path / "a" / "b" / "c.txt").resolve()


def test_resolve_under_staging_rejects_traversal_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes staging"):
        resolve_under_staging(tmp_path, "../outside.txt")
