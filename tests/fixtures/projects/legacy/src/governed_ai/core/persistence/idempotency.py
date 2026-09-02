"""Idempotency key store for Command Gateway (CG-004, CG-005)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.atomic import atomic_write_text


def payload_fingerprint(envelope: dict[str, Any]) -> str:
    material = {
        "type": envelope.get("type"),
        "actor": envelope.get("actor"),
        "target": envelope.get("target"),
        "payload": envelope.get("payload"),
        "human_authorization": envelope.get("human_authorization"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    idempotency_key: str
    payload_hash: str
    receipt: dict[str, Any]
    stored_at: str


class IdempotencyStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path_for(self, idempotency_key: str) -> Path:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return self._directory / f"{digest}.json"

    def lookup(self, idempotency_key: str, payload_hash: str) -> dict[str, Any] | None:
        path = self._path_for(idempotency_key)
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["payload_hash"] != payload_hash:
            raise GatewayError(
                ErrorCode.IDEMPOTENCY_MISMATCH,
                "idempotency key reused with different payload",
                "/idempotency_key",
            )
        return record["receipt"]

    def store(
        self,
        idempotency_key: str,
        payload_hash: str,
        receipt: dict[str, Any],
    ) -> None:
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            receipt=receipt,
            stored_at=datetime.now(UTC).isoformat(),
        )
        atomic_write_text(
            self._path_for(idempotency_key),
            json.dumps(
                {
                    "idempotency_key": record.idempotency_key,
                    "payload_hash": record.payload_hash,
                    "receipt": record.receipt,
                    "stored_at": record.stored_at,
                },
                indent=2,
            )
            + "\n",
        )
