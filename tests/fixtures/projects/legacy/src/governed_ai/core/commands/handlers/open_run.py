"""OpenRun command handler (Document 6 §9.1, §8)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.convergence import (
    DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP,
    DEFAULT_MAXIMUM_REMEDIATION_CYCLES,
)
from governed_ai.core.domain.run.execution_ceiling import (
    DEFAULT_EXECUTION_CEILING,
    validate_execution_ceiling,
)
from governed_ai.core.domain.run.parallelism import DEFAULT_MAXIMUM_PARALLEL_WORKERS
from governed_ai.core.domain.run.preflight import blocking_preflight_checks
from governed_ai.core.domain.run.autonomy_policy import UNATTENDED_PRESETS
from governed_ai.core.domain.run.mission_artifact import compute_artifact_hash
from governed_ai.core.domain.run.unattended_readiness import build_unattended_readiness_report
from governed_ai.core.persistence.transaction import Transaction


def handle_open_run(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    run_id = target["id"]
    payload = envelope["payload"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if run_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"run {run_id!r} already exists",
            "/target/id",
        )

    # Document 6 §9.6 — mechanical, not agent-judged: a check left fail/blocked/manual
    # forbids opening an unattended Run, regardless of preset.
    blocking = blocking_preflight_checks(payload["preflight"])
    if blocking:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"unattended run blocked by preflight checks: {', '.join(blocking)}",
            "/payload/preflight",
        )

    now = datetime.now(UTC).isoformat()
    document = dict(payload)
    document["id"] = run_id
    document.setdefault("status", "pending")
    document.setdefault("leases_by_work_unit", {})
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now
    document.setdefault("closed_at", None)
    document.setdefault("closed_reason", None)
    document.setdefault("stop_condition", None)
    document.setdefault("maximum_attempts_per_step", DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP)
    document.setdefault("maximum_remediation_cycles", DEFAULT_MAXIMUM_REMEDIATION_CYCLES)
    document.setdefault("maximum_parallel_workers", DEFAULT_MAXIMUM_PARALLEL_WORKERS)
    # Document 6 §9.8 — dedicated to this Run, distinct from individual Work Unit branches.
    document.setdefault("integration_branch", f"integration/{run_id}")

    # Document 6 §7.1/§7.2 — resolved once at open time, then fixed for the Run.
    # protected_branch_merge and production_action are pinned to forbidden for
    # every unattended preset; no ceiling supplied here can override that.
    requested_ceilings = payload.get("execution_ceilings_by_work_unit") or {}
    resolved_ceilings: dict[str, dict[str, str]] = {}
    for work_unit_id in document["work_unit_ids"]:
        ceiling = dict(DEFAULT_EXECUTION_CEILING)
        ceiling.update(requested_ceilings.get(work_unit_id) or {})
        violation = validate_execution_ceiling(ceiling)
        if violation is not None:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"work unit {work_unit_id!r}: {violation}",
                "/payload/execution_ceilings_by_work_unit",
            )
        resolved_ceilings[work_unit_id] = ceiling
    document["execution_ceilings_by_work_unit"] = resolved_ceilings

    if document["status"] not in {"pending", "active"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "initial status must be pending or active",
            "/payload/status",
        )

    # Document 6 §8 — authorize_run_grant() already validated this grant covers
    # the requested work units and has uses remaining; binding it here (and
    # spending one use) is the only place that actually happens.
    grant_id = envelope["run_authorization"]["grant_id"]
    grant_path = workspace_root.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    grant_document = json.loads(grant_path.read_text(encoding="utf-8"))

    autonomy_preset = payload.get("autonomy_preset") or grant_document.get("autonomy_preset")
    if autonomy_preset in UNATTENDED_PRESETS:
        if autonomy_preset != grant_document.get("autonomy_preset"):
            raise GatewayError(
                ErrorCode.UNAUTHORIZED,
                "Run autonomy preset does not match its authorization grant",
                "/payload/autonomy_preset",
            )
        work_units: dict[str, dict[str, Any] | None] = {}
        for work_unit_id in document["work_unit_ids"]:
            work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
            if work_unit_path.is_file():
                import yaml

                work_units[work_unit_id] = yaml.safe_load(
                    work_unit_path.read_text(encoding="utf-8")
                )
            else:
                work_units[work_unit_id] = None
        mission_artifacts = []
        for artifact_id in grant_document.get("mission_artifact_ids") or []:
            artifact_path = workspace_root.ai_team / "mission-artifacts" / f"{artifact_id}.json"
            if not artifact_path.is_file():
                raise GatewayError(
                    ErrorCode.INVARIANT_VIOLATION,
                    f"mission artifact {artifact_id!r} disappeared after grant issuance",
                    "/run_authorization/grant_id",
                )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            expected_hash = (grant_document.get("mission_artifact_hashes") or {}).get(artifact_id)
            if expected_hash != compute_artifact_hash(artifact):
                raise GatewayError(
                    ErrorCode.INVARIANT_VIOLATION,
                    f"mission artifact {artifact_id!r} changed after grant issuance",
                    "/run_authorization/grant_id",
                )
            mission_artifacts.append(artifact)
        readiness = build_unattended_readiness_report(
            preset=autonomy_preset,
            work_unit_documents=work_units,
            execution_ceilings_by_work_unit=requested_ceilings,
            grant=grant_document,
            mission_artifacts=mission_artifacts,
        )
        if not readiness["ready"]:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"unattended readiness failed: {readiness['gaps']}",
                "/payload/autonomy_preset",
            )
        document["effective_autonomy_policy"] = grant_document["effective_autonomy_policy"]
        document["effective_autonomy_policy_hash"] = grant_document[
            "effective_autonomy_policy_hash"
        ]
    else:
        document["effective_autonomy_policy"] = None
        document["effective_autonomy_policy_hash"] = None
    document["autonomy_preset"] = autonomy_preset or "supervised_copilots"
    grant_document["uses_count"] = grant_document.get("uses_count", 0) + 1
    transaction.plan_json_write(grant_path, grant_document)
    document["run_authorization_grant_id"] = grant_id

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "run.schema.json",
        root_path="",
    )

    transaction.plan_yaml_write(run_path, document)
    return {
        "affected": [
            {
                "kind": "run",
                "id": run_id,
                "revision": 1,
                "status": document["status"],
            }
        ],
    }, []
