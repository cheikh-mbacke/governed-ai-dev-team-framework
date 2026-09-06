"""Golden vector for Feedback Export HMAC-SHA256-V1 (tunnel-compatible)."""

from __future__ import annotations

import base64

from governed_ai.feedback.hmac_v1 import build_canonical_v1, compute_signature_v1, sign_v1


def test_hmac_v1_canonical_vector() -> None:
    secret = base64.b64decode("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
    canonical = build_canonical_v1(
        key_id="key-test-01",
        timestamp="1788432000",
        nonce="2ac23471-7f75-4e8a-9117-bdb7b705991d",
        content_sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    assert not canonical.endswith(b"\n")
    sig = sign_v1(secret, canonical)
    assert sig == "v1=049c21ee38684063dca37864108a88cf2dc41267cfa9423aef9d15e870a09cea"
    assert (
        compute_signature_v1(
            secret,
            key_id="key-test-01",
            timestamp="1788432000",
            nonce="2ac23471-7f75-4e8a-9117-bdb7b705991d",
            content_sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )
        == sig
    )
