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
            lock: ProjectLock | None = None
            try:
                lock = acquire_project_lock(self._lock_path)
                # Reads that participate in authorization or idempotency must
                # be serialized with writes too. On Windows, reading a file
                # while another thread atomically replaces it can raise a
                # mandatory-sharing PermissionError; more importantly, doing
                # these checks before the lock creates a TOCTOU window where a
                # grant can be revoked between authorization and mutation.
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
        if name == "run-morning-report":
            query_args = args or {}
            run_id = query_args.get("run_id")
            if not run_id:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "run_id is required",
                    "/query/run_id",
                )
            report = self._build_run_morning_report(run_id)
            return {"name": name, "data": report}
        if name == "unattended-readiness":
            query_args = args or {}
            preset = query_args.get("preset")
            if not preset:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA, "preset is required", "/query/preset"
                )
            work_unit_ids = query_args.get("work_unit_ids") or []
            if not work_unit_ids:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "work_unit_ids is required and must be non-empty",
                    "/query/work_unit_ids",
                )
            grant_id = query_args.get("grant_id")
            if not grant_id:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA, "grant_id is required", "/query/grant_id"
                )
            report = self._build_unattended_readiness_report(
                preset=preset,
                work_unit_ids=work_unit_ids,
                grant_id=grant_id,
                execution_ceilings_by_work_unit=query_args.get("execution_ceilings_by_work_unit"),
            )
            return {"name": name, "data": report}
        raise GatewayError(ErrorCode.INVALID_SCHEMA, f"unknown query {name!r}", "/query")

    def _build_run_morning_report(self, run_id: str) -> dict[str, Any]:
        import yaml

        from governed_ai.core.domain.run.morning_report import build_morning_report

        run_path = self._ai_team / "runs" / f"{run_id}.yaml"
        if not run_path.is_file():
            raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/query/run_id")
        run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))

        work_unit_documents: dict[str, Any] = {}
        for work_unit_id in run_document.get("work_unit_ids") or []:
            path = self._ai_team / "work-units" / f"{work_unit_id}.yaml"
            work_unit_documents[work_unit_id] = (
                yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
            )

        def _load_dir(name: str) -> list[dict[str, Any]]:
            directory = self._ai_team / "runs" / name
            if not directory.is_dir():
                return []
            return [
                yaml.safe_load(path.read_text(encoding="utf-8"))
                for path in sorted(directory.glob("*.yaml"))
            ]

        def _for_run(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [item for item in items if item.get("run_id") == run_id]

        attempts = _for_run(_load_dir("execution-attempts"))
        leases = _for_run(_load_dir("leases"))
        decisions = _for_run(_load_dir("decisions"))
        escalations = _for_run(_load_dir("escalations"))
        integration_merges = _for_run(_load_dir("integration-merges"))

        release_candidates = []
        candidates_dir = self._ai_team / "release-candidates"
        if candidates_dir.is_dir():
            release_candidates = [
                document
                for path in sorted(candidates_dir.glob("*.yaml"))
                if (document := yaml.safe_load(path.read_text(encoding="utf-8"))).get("run_id")
                == run_id
            ]

        events_dir = self._ai_team / "events"
        events = []
        if events_dir.is_dir():
            for path in sorted(events_dir.glob("*.yaml")):
                event = yaml.safe_load(path.read_text(encoding="utf-8"))
                if (event.get("details") or {}).get("run_id") == run_id:
                    events.append(event)

        return build_morning_report(
            run_document=run_document,
            work_unit_documents=work_unit_documents,
            attempts=attempts,
            leases=leases,
            decisions=decisions,
            escalations=escalations,
            events=events,
            integration_merges=integration_merges,
            release_candidates=release_candidates,
        )

    def _build_unattended_readiness_report(
        self,
        *,
        preset: str,
        work_unit_ids: list[str],
        grant_id: str,
        execution_ceilings_by_work_unit: dict[str, Any] | None,
    ) -> dict[str, Any]:
        import yaml

        from governed_ai.core.domain.run.unattended_readiness import (
            build_unattended_readiness_report,
        )

        work_unit_documents: dict[str, Any] = {}
        for work_unit_id in work_unit_ids:
            path = self._ai_team / "work-units" / f"{work_unit_id}.yaml"
            work_unit_documents[work_unit_id] = (
                yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
            )

        grant_path = self._ai_team / "run-authorization-grants" / f"{grant_id}.json"
        if not grant_path.is_file():
            raise GatewayError(
                ErrorCode.NOT_FOUND, f"run authorization grant {grant_id!r} not found", "/query/grant_id"
            )
        grant = json.loads(grant_path.read_text(encoding="utf-8"))

        mission_artifacts = []
        for artifact_id in grant.get("mission_artifact_ids") or []:
            artifact_path = self._ai_team / "mission-artifacts" / f"{artifact_id}.json"
            if artifact_path.is_file():
                mission_artifacts.append(json.loads(artifact_path.read_text(encoding="utf-8")))

        return build_unattended_readiness_report(
            preset=preset,
            work_unit_documents=work_unit_documents,
            execution_ceilings_by_work_unit=execution_ceilings_by_work_unit,
            grant=grant,
            mission_artifacts=mission_artifacts,
        )

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
