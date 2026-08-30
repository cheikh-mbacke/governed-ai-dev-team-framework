"""Command Gateway entrypoint."""

from __future__ import annotations

import json
from typing import Any

from governed_ai.core.commands.authorization import authorize_command
from governed_ai.core.commands.envelope import parse_envelope
from governed_ai.core.commands.errors import ErrorCode, GatewayError, exit_code_for
from governed_ai.core.commands.handlers import HANDLERS
from governed_ai.core.commands.receipt import build_receipt, build_rejected_receipt
from governed_ai.core.persistence.idempotency import IdempotencyStore, payload_fingerprint
from governed_ai.core.persistence.lock import ProjectLock, acquire_project_lock
from governed_ai.core.persistence.transaction import Transaction, recover_transactions
from governed_ai.core.workspace import Workspace


class CommandGateway:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._ai_team = workspace.ai_team
        self._transactions_root = self._ai_team / ".transactions"
        self._idempotency = IdempotencyStore(self._transactions_root / "idempotency")
        self._lock_path = self._ai_team / "locks" / "project.lock"

    def execute_command(self, raw_envelope: dict[str, Any]) -> tuple[dict[str, Any], int]:
        command_id = str(raw_envelope.get("command_id") or "")
        try:
            envelope = parse_envelope(raw_envelope)
            command_id = envelope["command_id"]
            payload_hash = payload_fingerprint(envelope)
            cached = self._idempotency.lookup(envelope["idempotency_key"], payload_hash)
            if cached is not None:
                return cached, 0

            authorize_command(envelope, self._ai_team)

            handler = HANDLERS.get(envelope["type"])
            if handler is None:
                raise GatewayError(
                    ErrorCode.UNSUPPORTED_CONTRACT,
                    f"unsupported command type {envelope['type']!r}",
                    "/type",
                )

            lock: ProjectLock | None = None
            try:
                lock = acquire_project_lock(self._lock_path)
                transaction = Transaction.begin(self._transactions_root)
                result, domain_events = handler(
                    envelope,
                    workspace_root=self._workspace,
                    transaction=transaction,
                )
                transaction.commit()
                receipt = build_receipt(
                    command_id=command_id,
                    transaction_id=transaction.transaction_id,
                    status="accepted",
                    affected=result.get("affected", []),
                    domain_events=domain_events,
                    details=result.get("details"),
                )
                self._idempotency.store(
                    envelope["idempotency_key"],
                    payload_hash,
                    receipt,
                )
                return receipt, 0
            finally:
                if lock is not None:
                    lock.release()
        except GatewayError as exc:
            receipt = build_rejected_receipt(command_id or "CMD-unknown", exc)
            return receipt, exit_code_for(exc.code)

    def recover(self) -> dict[str, Any]:
        messages = recover_transactions(self._transactions_root, self._workspace.root)
        return {"status": "ok", "messages": messages}

    def query(self, name: str, *, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if name == "project-state":
            path = self._ai_team / "state" / "project-state.yaml"
            if not path.is_file():
                raise GatewayError(ErrorCode.NOT_FOUND, "project state not found", "/query")
            import yaml

            return {"name": name, "data": yaml.safe_load(path.read_text(encoding="utf-8"))}
        if name == "work-unit-done":
            query_args = args or {}
            work_unit_id = query_args.get("work_unit_id")
            if not work_unit_id:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "work_unit_id is required",
                    "/query/work_unit_id",
                )
            from governed_ai.core.domain.work_unit.done import missing_done_prerequisites
            from governed_ai.core.domain.work_unit.paths import find_work_unit_path

            path, ambiguity = find_work_unit_path(self._ai_team / "work-units", work_unit_id)
            if ambiguity:
                raise GatewayError(ErrorCode.INVALID_SCHEMA, ambiguity, "/query/work_unit_id")
            if path is None:
                raise GatewayError(
                    ErrorCode.NOT_FOUND,
                    f"work unit {work_unit_id!r} not found",
                    "/query/work_unit_id",
                )
            import yaml

            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            missing = missing_done_prerequisites(document)
            return {
                "name": name,
                "work_unit_id": work_unit_id,
                "done": not missing,
                "missing": missing,
            }
        raise GatewayError(ErrorCode.INVALID_SCHEMA, f"unknown query {name!r}", "/query")

    def validate_gateway(self) -> dict[str, Any]:
        pending = [
            path.parent.name
            for path in self._transactions_root.glob("TX-*/journal.json")
            if json.loads(path.read_text(encoding="utf-8")).get("status") == "prepared"
        ]
        return {
            "status": "ok" if not pending else "recovery_required",
            "pending_transactions": pending,
        }


def load_envelope_from_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "invalid JSON input", "") from exc
