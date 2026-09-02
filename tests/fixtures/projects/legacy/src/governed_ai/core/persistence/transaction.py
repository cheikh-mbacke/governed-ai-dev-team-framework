"""Transactional journal and recovery (Document 11 §7.3)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.atomic import atomic_write_bytes, atomic_write_text
from governed_ai.core.persistence.failpoints import Failpoint, check_failpoint


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _journal_integrity_hash(writes: list[dict[str, Any]], domain_events: list[dict[str, Any]]) -> str:
    payload = json.dumps({"writes": writes, "domain_events": domain_events}, sort_keys=True)
    return _sha256_text(payload)


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
    planned: list[PlannedWrite] = field(default_factory=list)
    planned_domain_events: list[PlannedWrite] = field(default_factory=list)

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

    def plan_json_write(self, absolute_path: Path, new_document: Any) -> None:
        rel = absolute_path.relative_to(self.workspace_root).as_posix()
        new_text = json.dumps(new_document, indent=2) + "\n"
        before_hash = None
        if absolute_path.is_file():
            before_hash = _sha256_text(absolute_path.read_text(encoding="utf-8"))
        self.planned.append(
            PlannedWrite(relative_path=rel, content=new_text, before_hash=before_hash)
        )

    def plan_domain_event(self, absolute_path: Path, event_document: dict[str, Any]) -> None:
        rel = absolute_path.relative_to(self.workspace_root).as_posix()
        new_text = json.dumps(event_document, indent=2) + "\n"
        if absolute_path.is_file():
            raise GatewayError(
                ErrorCode.ALREADY_EXISTS,
                f"domain event {absolute_path.name!r} already exists",
                "/domain_events",
            )
        self.planned_domain_events.append(
            PlannedWrite(relative_path=rel, content=new_text, before_hash=None)
        )

    def _build_journal_writes(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        writes = [
            {
                "relative_path": item.relative_path,
                "before_hash": item.before_hash,
                "after_hash": _sha256_text(item.content),
            }
            for item in self.planned
        ]
        domain_events = [
            {
                "relative_path": item.relative_path,
                "before_hash": item.before_hash,
                "after_hash": _sha256_text(item.content),
            }
            for item in self.planned_domain_events
        ]
        return writes, domain_events

    def commit(self) -> None:
        if not self.planned and not self.planned_domain_events:
            raise GatewayError(ErrorCode.INTERNAL_ERROR, "transaction has no planned writes")

        check_failpoint(Failpoint.BEFORE_JOURNAL)
        writes, domain_events = self._build_journal_writes()
        journal_payload: dict[str, Any] = {
            "transaction_id": self.transaction_id,
            "status": "prepared",
            "started_at": datetime.now(UTC).isoformat(),
            "writes": writes,
            "domain_events": domain_events,
            "integrity_hash": _journal_integrity_hash(writes, domain_events),
        }

        for index, item in enumerate(self.planned):
            staging = self.journal_dir / f"stage-{index}.tmp"
            atomic_write_bytes(staging, item.content.encode("utf-8"))
        for index, item in enumerate(self.planned_domain_events):
            staging = self.journal_dir / f"event-stage-{index}.tmp"
            atomic_write_bytes(staging, item.content.encode("utf-8"))

        atomic_write_text(
            self.journal_path,
            json.dumps(journal_payload, indent=2) + "\n",
        )
        check_failpoint(Failpoint.AFTER_JOURNAL)

        for index, item in enumerate(self.planned):
            target = self.workspace_root / item.relative_path
            staging = self.journal_dir / f"stage-{index}.tmp"
            check_failpoint(Failpoint.AFTER_STAGING, index=index)
            atomic_write_bytes(target, staging.read_bytes())
            check_failpoint(Failpoint.AFTER_REPLACE, index=index)

        check_failpoint(Failpoint.BEFORE_DOMAIN_EVENTS)
        for index, item in enumerate(self.planned_domain_events):
            target = self.workspace_root / item.relative_path
            staging = self.journal_dir / f"event-stage-{index}.tmp"
            atomic_write_bytes(target, staging.read_bytes())
        check_failpoint(Failpoint.AFTER_DOMAIN_EVENTS)

        journal_payload["status"] = "committed"
        journal_payload["committed_at"] = datetime.now(UTC).isoformat()
        journal_payload["integrity_hash"] = _journal_integrity_hash(writes, domain_events)
        atomic_write_text(self.journal_path, json.dumps(journal_payload, indent=2) + "\n")


def _verify_journal_integrity(journal: dict[str, Any]) -> None:
    writes = journal.get("writes") or []
    domain_events = journal.get("domain_events") or []
    expected = journal.get("integrity_hash")
    if not expected:
        return
    actual = _journal_integrity_hash(writes, domain_events)
    if actual != expected:
        raise GatewayError(
            ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
            f"journal integrity hash mismatch for {journal.get('transaction_id')}",
            "/integrity_hash",
        )


def _verify_staging_hashes(journal: dict[str, Any], tx_dir: Path) -> None:
    for index, write in enumerate(journal.get("writes") or []):
        staging = tx_dir / f"stage-{index}.tmp"
        if not staging.is_file():
            continue
        staging_hash = _sha256_bytes(staging.read_bytes())
        if staging_hash != write.get("after_hash"):
            raise GatewayError(
                ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                f"staging hash mismatch for write {index}",
                f"/writes/{index}/after_hash",
            )
    for index, event in enumerate(journal.get("domain_events") or []):
        staging = tx_dir / f"event-stage-{index}.tmp"
        if not staging.is_file():
            continue
        staging_hash = _sha256_bytes(staging.read_bytes())
        if staging_hash != event.get("after_hash"):
            raise GatewayError(
                ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                f"staging hash mismatch for domain event {index}",
                f"/domain_events/{index}/after_hash",
            )


def _target_matches_hash(target: Path, expected_hash: str | None) -> bool:
    if expected_hash is None:
        return False
    if not target.is_file():
        return False
    return _sha256_text(target.read_text(encoding="utf-8")) == expected_hash


def _apply_pending_writes(journal: dict[str, Any], tx_dir: Path, workspace_root: Path) -> None:
    for index, write in enumerate(journal.get("writes") or []):
        target = workspace_root / write["relative_path"]
        staging = tx_dir / f"stage-{index}.tmp"
        before_hash = write.get("before_hash")
        after_hash = write.get("after_hash")

        if _target_matches_hash(target, after_hash):
            continue

        if target.is_file() and before_hash:
            current_hash = _sha256_text(target.read_text(encoding="utf-8"))
            if current_hash != before_hash:
                raise GatewayError(
                    ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                    f"cannot recover transaction {journal['transaction_id']} safely",
                    f"/writes/{index}",
                )

        if staging.is_file():
            atomic_write_bytes(target, staging.read_bytes())
        elif not _target_matches_hash(target, after_hash):
            raise GatewayError(
                ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                f"missing staging file for write {index}",
                f"/writes/{index}",
            )


def _apply_pending_domain_events(journal: dict[str, Any], tx_dir: Path, workspace_root: Path) -> None:
    for index, event in enumerate(journal.get("domain_events") or []):
        target = workspace_root / event["relative_path"]
        if target.is_file():
            if _target_matches_hash(target, event.get("after_hash")):
                continue
            raise GatewayError(
                ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                f"domain event path already exists with unexpected content: {event['relative_path']}",
                f"/domain_events/{index}",
            )
        staging = tx_dir / f"event-stage-{index}.tmp"
        if staging.is_file():
            atomic_write_bytes(target, staging.read_bytes())
        else:
            raise GatewayError(
                ErrorCode.TRANSACTION_RECOVERY_REQUIRED,
                f"missing staging file for domain event {index}",
                f"/domain_events/{index}",
            )


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

        try:
            _verify_journal_integrity(journal)
            _verify_staging_hashes(journal, tx_dir)
            _apply_pending_writes(journal, tx_dir, workspace_root)
            _apply_pending_domain_events(journal, tx_dir, workspace_root)
        except GatewayError:
            raise

        journal["status"] = "committed"
        journal["committed_at"] = datetime.now(UTC).isoformat()
        journal["recovered"] = True
        atomic_write_text(journal_path, json.dumps(journal, indent=2) + "\n")
        messages.append(f"recovered transaction {journal['transaction_id']}")

    return messages
