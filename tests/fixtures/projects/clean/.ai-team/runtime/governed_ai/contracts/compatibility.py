"""Compatibility negotiation and active-bundle resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from governed_ai.contracts.publish import ACTIVE_BUNDLE_NAME, BUNDLES_DIR_NAME


class CompatibilityIssue(TypedDict, total=False):
    """Single incompatibility or fallback note (Document 12 §4)."""

    code: str
    path: str
    required: str
    available: str
    fallback: str


class CompatibilityReport(TypedDict):
    """Result of adapter compatibility check (Document 12 §4)."""

    compatible: bool
    adapter_id: str
    role_id: str
    procedure_id: str
    issues: list[CompatibilityIssue]


class ActiveBundlePointer(TypedDict):
    """Pointer written at ``active-bundle.json`` (Document 11 §4)."""

    bundle_version: str
    path: str
    content_hash: str


def load_active_bundle_pointer(contracts_root: Path) -> ActiveBundlePointer:
    """Load and validate the active-bundle pointer under ``contracts_root``."""
    path = contracts_root / ACTIVE_BUNDLE_NAME
    if not path.is_file():
        raise FileNotFoundError(f"missing {ACTIVE_BUNDLE_NAME} under {contracts_root}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("active-bundle.json root must be an object")
    version = data.get("bundle_version")
    rel = data.get("path")
    digest = data.get("content_hash")
    if not isinstance(version, str) or not version:
        raise ValueError("active-bundle.json missing bundle_version")
    if not isinstance(rel, str) or not rel:
        raise ValueError("active-bundle.json missing path")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ValueError("active-bundle.json missing or invalid content_hash")
    return ActiveBundlePointer(
        bundle_version=version,
        path=rel,
        content_hash=digest,
    )


def resolve_active_bundle_dir(contracts_root: Path) -> Path:
    """Resolve the published directory referenced by ``active-bundle.json``."""
    pointer = load_active_bundle_pointer(contracts_root)
    root = contracts_root.resolve()
    bundle_dir = (root / pointer["path"]).resolve()
    if not bundle_dir.is_relative_to(root):
        raise ValueError(f"active bundle path escapes contracts root: {pointer['path']}")
    if not bundle_dir.is_dir():
        # Fall back to conventional layout if pointer path is odd but version is set.
        conventional = root / BUNDLES_DIR_NAME / pointer["bundle_version"]
        if conventional.is_dir():
            return conventional
        raise FileNotFoundError(f"active bundle directory missing: {bundle_dir}")
    return bundle_dir


__all__ = [
    "ActiveBundlePointer",
    "CompatibilityIssue",
    "CompatibilityReport",
    "load_active_bundle_pointer",
    "resolve_active_bundle_dir",
]
