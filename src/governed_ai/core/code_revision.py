"""Normalize Evidence / Work Unit code_revision values (Document 25).

Standalone continues to persist a SHA string. Ensemble product evidence uses a
composition object. This module does not mutate governance state.
"""

from __future__ import annotations

from typing import Any

GIT_COMMIT = "git_commit"
COMPOSITION = "composition"


def normalize_code_revision(value: Any) -> dict[str, Any] | None:
    """Return a canonical mapping, or ``None`` when the revision is unknown.

    A non-empty string is treated as ``kind: git_commit`` (0.7.x standalone).
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("code_revision string must be non-empty")
        return {"kind": GIT_COMMIT, "sha": value}
    if not isinstance(value, dict):
        raise TypeError("code_revision must be a string, object, or null")
    kind = value.get("kind")
    if kind == GIT_COMMIT:
        sha = value.get("sha")
        if not isinstance(sha, str) or not sha.strip():
            raise ValueError("git_commit code_revision requires sha")
        normalized: dict[str, Any] = {"kind": GIT_COMMIT, "sha": sha}
        member_id = value.get("member_id")
        if member_id is not None:
            if not isinstance(member_id, str) or not member_id:
                raise ValueError("member_id must be a non-empty string")
            normalized["member_id"] = member_id
        return normalized
    if kind == COMPOSITION:
        composition_id = value.get("composition_id")
        if not isinstance(composition_id, str) or not composition_id.startswith("CR-"):
            raise ValueError("composition code_revision requires composition_id CR-*")
        normalized = {"kind": COMPOSITION, "composition_id": composition_id}
        members = value.get("members")
        if members is not None:
            if not isinstance(members, dict) or not members:
                raise ValueError("composition members must be a non-empty object")
            normalized["members"] = dict(members)
        return normalized
    raise ValueError(f"unsupported code_revision kind: {kind!r}")
