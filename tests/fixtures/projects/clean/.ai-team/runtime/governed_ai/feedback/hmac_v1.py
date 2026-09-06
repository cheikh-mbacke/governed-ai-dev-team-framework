"""HMAC-SHA256 v1 helpers for Feedback Export ingest (vendored tunnel algorithm).

Do not import the ingestion package; keep the framework offline-capable.
"""

from __future__ import annotations

import hashlib
import hmac

CANONICAL_PREFIX = "GAI-HMAC-SHA256-V1"
DEFAULT_PATH = "/v1/feedback-exports"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_canonical_v1(
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    content_sha256: str,
    method: str = "POST",
    path: str = DEFAULT_PATH,
) -> bytes:
    """Build the exact UTF-8 bytes signed by HMAC v1 (no trailing LF)."""
    parts = [
        CANONICAL_PREFIX,
        method,
        path,
        key_id,
        timestamp,
        nonce,
        content_sha256,
    ]
    return "\n".join(parts).encode("utf-8")


def sign_v1(secret: bytes, canonical: bytes) -> str:
    digest = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def compute_signature_v1(
    secret: bytes,
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    content_sha256: str,
    method: str = "POST",
    path: str = DEFAULT_PATH,
) -> str:
    canonical = build_canonical_v1(
        key_id=key_id,
        timestamp=timestamp,
        nonce=nonce,
        content_sha256=content_sha256,
        method=method,
        path=path,
    )
    return sign_v1(secret, canonical)
