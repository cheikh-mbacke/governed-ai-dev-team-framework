"""Managed file ownership classification for Installation Record."""

from __future__ import annotations

import sys
from pathlib import Path

from distribution.installer.record import normalize_path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts" / "ai-team"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from validate_ownership import classify_owner  # noqa: E402

OWNER_CORE = "core"
OWNER_CURSOR = "adapter:cursor"
OWNER_DISTRIBUTION = "distribution"
OWNER_PROJECT = "project"

V2_OWNER_BUCKETS = frozenset({OWNER_CORE, OWNER_CURSOR, OWNER_DISTRIBUTION})


class UnclassifiableManagedFileError(ValueError):
    """Raised when a legacy managed_file cannot be assigned an owner."""


def classify_managed_file(path: str | Path) -> str:
    """Classify a framework-managed path into an Installation Record owner bucket."""
    normalized = normalize_path(path)

    if normalized == ".ai-team/installation-record.json":
        return OWNER_DISTRIBUTION
    if normalized == ".ai-team/requirements.txt":
        return OWNER_CORE
    if normalized.startswith(".ai-team/runtime/governed_ai/adapters/cursor/"):
        return OWNER_CURSOR
    if normalized.startswith(".ai-team/runtime/governed_ai/"):
        return OWNER_CORE
    # Legacy installed layout (pre-0.7.0) — still classifiable during migration.
    if normalized.startswith("docs/product/"):
        return OWNER_CORE
    if normalized.startswith("docs/operator/"):
        return OWNER_CORE
    if normalized == "README.md":
        return OWNER_CORE
    if normalized.startswith("src/"):
        return OWNER_CORE
    if normalized.startswith("adapters/cursor/"):
        return OWNER_CURSOR
    if normalized == "requirements.txt":
        return OWNER_CORE
    if normalized.startswith(".ai-team/contracts/"):
        return OWNER_CORE

    try:
        owner = classify_owner(normalized)
    except ValueError as exc:
        raise UnclassifiableManagedFileError(str(exc)) from exc

    if owner == OWNER_PROJECT:
        raise UnclassifiableManagedFileError(
            f"Managed file classified as project-owned: {normalized}"
        )
    return owner


def partition_managed_files(paths: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        OWNER_CORE: [],
        OWNER_CURSOR: [],
        OWNER_DISTRIBUTION: [],
    }
    for raw in paths:
        owner = classify_managed_file(raw)
        if owner not in V2_OWNER_BUCKETS:
            raise UnclassifiableManagedFileError(f"Unsupported owner bucket: {owner}")
        buckets[owner].append(normalize_path(raw))

    for key in buckets:
        buckets[key] = sorted(set(buckets[key]))
    return buckets
