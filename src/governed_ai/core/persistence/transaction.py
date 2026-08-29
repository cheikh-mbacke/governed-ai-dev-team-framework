"""Transactional journal and recovery (Document 11 §7.3)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.atomic import atomic_write_bytes, atomic_write_text


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    relative_path: str
    content: str
    before_hash: str | None


@dataclass(slots=True)
class Transaction:
    workspace_root: Path
    transaction_id: str
    journal_dir: Path
    journal_path: Path
    planned: list[PlannedWrite]

    @classmethod
    def begin(cls, transactions_root: Path) -> Transaction:
        transaction_id = f"TX-{uuid.uuid4()}"
        journal_dir = transactions_root / transaction_id
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / "journal.json"
        return cls(
            workspace_root=transactions_root.parent.parent,
            transaction_id=transaction_id,
            journal_dir=journal_dir,
            journal_path=journal_path,
            planned=[],
        )

    def plan_yaml_write(self, absolute_path: Path, new_document: Any) -> None:
        rel = absolute_path.relative_to(self.workspace_root).as_posix()
        new_text = yaml.safe_dump(new_document, sort_keys=False, allow_unicode=True)
        before_hash = None
        if absolute_path.is_file():
            before_hash = _sha256_text(absolute_path.read_text(encoding="utf-8"))
        self.planned.append(
            PlannedWrite(relative_path=rel, content=new_text, before_hash=before_hash)
        )

    def commit(self) -> None:
        if not self.planned:
            raise GatewayError(ErrorCode.INTERNAL_ERROR, "transaction has no planned writes")

        journal_payload = {
            "transaction_id": self.transaction_id,
            "status": "prepared",
            "started_at": datetime.now(UTC).isoformat(),
            "writes": [
                {
                    "relative_path": item.relative_path,
                    "before_hash": item.before_hash,
                    "after_hash": _sha256_text(item.content),
                }
                for item in self.planned
            ],
        }
        atomic_write_text(
            self.journal_path,
            json.dumps(journal_payload, indent=2) + "\n",
        )

        for index, item in enumerate(self.planned):
            target = self.workspace_root / item.relative_path
            staging = self.journal_dir / f"stage-{index}.tmp"
            atomic_write_bytes(staging, item.content.encode("utf-8"))
            atomic_write_bytes(target, item.content.encode("utf-8"))

        journal_payload["status"] = "committed"
        journal_payload["committed_at"] = datetime.now(UTC).isoformat()
        atomic_write_text(self.journal_path, json.dumps(journal_payload, indent=2) + "\n")


def recover_transactions(transactions_root: Path, workspace_root: Path) -> list[str]:
    """Finalize or abort pending transactions deterministically."""
    if not transactions_root.is_dir():
        return []

    messages: list[str] = []
    for journal_path in sorted(transactions_root.glob("TX-*/journal.json")):
        try:
            raw = journal_path.read_text(encoding="utf-8")
            journal = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            journal_path.unlink(missing_ok=True)
            messages.append(f"removed invalid journal {journal_path.name}")
            continue

        status = journal.get("status")
        tx_dir = journal_path.parent
        if status == "committed":
            continue
        if status != "prepared":
            journal_path.unlink(missing_ok=True)
            messages.append(f"removed unknown-status journal {journal['transaction_id']}")
            continue

        for index, write in enumerate(journal.get("writes") or []):
            target = workspace_root / write["relative_path"]
            staging = tx_dir / f"stage-{index}.tmp"
            before_hash = write.get("before_hash")
            if target.is_file():
                current_hash = _sha256_text(target.read_text(encoding="utf-8"))
                if before_hash and current_hash != before_hash:
                    raise GatewayError(
                        ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                        f"cannot recover transaction {journal['transaction_id']} safely",
                        f"/writes/{index}",
                    )
            if staging.is_file():
                content = staging.read_bytes()
                if target.is_file() and before_hash:
                    current_hash = _sha256_text(target.read_text(encoding="utf-8"))
                    if current_hash == before_hash:
                        atomic_write_bytes(target, content)
                elif not target.is_file():
                    atomic_write_bytes(target, content)

        journal["status"] = "committed"
        journal["committed_at"] = datetime.now(UTC).isoformat()
        journal["recovered"] = True
        atomic_write_text(journal_path, json.dumps(journal, indent=2) + "\n")
        messages.append(f"recovered transaction {journal['transaction_id']}")

    return messages
