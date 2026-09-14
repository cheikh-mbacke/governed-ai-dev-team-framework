"""Content hashing for design artifacts and packages (Core-owned)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def stable_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_canonical(payload: Any) -> str:
    return sha256_text(stable_dumps(payload))


def assert_hash_match(*, expected: str, actual: str, code: str = "content_hash_mismatch") -> None:
    if str(expected) != str(actual):
        raise DesignHashError(code, expected=expected, actual=actual)


class DesignHashError(ValueError):
    def __init__(self, code: str, *, expected: str, actual: str) -> None:
        super().__init__(f"{code}: expected {expected!r} got {actual!r}")
        self.code = code
        self.expected = expected
        self.actual = actual
