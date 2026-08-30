"""Canonical content_hash for Published Contract Bundles (Document 12 §2.1).

Hash input (UTF-8 bytes, SHA-256 hex digest prefixed with ``sha256:``):

1. Canonical JSON of the manifest object **without** the ``content_hash``
   field (sorted keys, compact separators, ``ensure_ascii=False``).
2. For every path listed in ``roles`` and ``procedures``, sorted by path
   string: a length-prefixed path segment then the raw file bytes.

Length-prefixed segments avoid ambiguity between path and content:

``struct:`` ``\\x00`` + uint32_be(len(path_utf8)) + path_utf8
            + uint32_be(len(content)) + content
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic JSON bytes for hashing / comparison."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _referenced_paths(manifest: Mapping[str, Any]) -> list[str]:
    roles = list(manifest.get("roles") or [])
    procedures = list(manifest.get("procedures") or [])
    return sorted({*roles, *procedures})


def _length_prefixed(label: bytes, payload: bytes) -> bytes:
    return b"\x00" + struct.pack(">I", len(label)) + label + struct.pack(">I", len(payload)) + payload


def compute_bundle_content_hash(
    bundle_dir: Path,
    manifest: Mapping[str, Any],
) -> str:
    """Compute ``sha256:<hex>`` for a bundle directory and its manifest mapping."""
    digest = hashlib.sha256()
    without_hash = {k: v for k, v in manifest.items() if k != "content_hash"}
    digest.update(canonical_json_bytes(without_hash))

    root = bundle_dir.resolve()
    for rel in _referenced_paths(manifest):
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"referenced path escapes bundle root: {rel}")
        content = path.read_bytes()
        digest.update(_length_prefixed(rel.encode("utf-8"), content))

    return f"sha256:{digest.hexdigest()}"
