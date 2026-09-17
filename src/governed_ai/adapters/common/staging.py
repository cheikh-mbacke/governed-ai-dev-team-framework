"""Generic staging helpers shared by every Adaptateur compiler (AD-002, AD-012).

Extracted from ``adapters/cursor/compiler/staging.py`` — this module contains
only the parts of that file with zero Cursor-specific content. Cursor-specific
classification (``artifact_kind``, ``REQUIRED_TOP_LEVEL``) and the
``validate_pre_install`` gate that depends on them stay local to each
Adaptateur's own compiler package.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def resolve_under_staging(staging_root: Path, rel_path: str) -> Path:
    """Resolve a manifest-relative path and reject escapes (AD-012)."""
    staging_resolved = staging_root.resolve()
    candidate = (staging_root / rel_path).resolve()
    if not candidate.is_relative_to(staging_resolved):
        raise ValueError(f"artifact path escapes staging: {rel_path}")
    return candidate


__all__ = ["resolve_under_staging", "sha256_bytes"]
