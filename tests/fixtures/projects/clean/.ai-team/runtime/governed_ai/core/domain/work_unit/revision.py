"""Revision helpers for mutable Work Units."""

from __future__ import annotations

from typing import Any


class RevisionError(ValueError):
    """Invalid revision field on a Work Unit document."""


def current_revision(document: dict[str, Any]) -> int:
    revision = document.get("revision", 1)
    if not isinstance(revision, int):
        raise RevisionError("revision must be integer")
    return revision
