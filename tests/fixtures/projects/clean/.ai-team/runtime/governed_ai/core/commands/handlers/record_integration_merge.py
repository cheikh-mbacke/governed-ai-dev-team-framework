"""RecordIntegrationMerge command handler (Document 6 §9.8).

`integration-steward` supervises the merge queue into a Run's dedicated
integration branch — distinct from any individual Work Unit branch and
never the protected branch (`main`), which stays permanently forbidden via
`execution_ceiling.protected_branch_merge` (§7.1) regardless of anything
here. Conflict resolution is bounded by the same limit as the convergence
loop (§9.3); a merge without a passed revalidation is never recorded.
"""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run import fencing
from governed_ai.core.domain.run.convergence import DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP
from governed_ai.core.domain.run.execution_ceiling import DEFAULT_EXECUTION_CEILING
from governed_ai.core.persistence.transaction import Transaction


def handle_record_integration_merge(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    merge_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    work_unit_id = payload["work_unit_id"]
    epoch = payload["epoch"]
    attempts = payload["conflict_resolution_attempts"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))

    if (
        run_document.get("autonomy_preset", "supervised_copilots").startswith("unattended_")
        and run_document.get("status") != "active"
    ):
        raise GatewayError(ErrorCode.INVARIANT_VIOLATION, f"run {run_id!r} is not active")

    if not fencing.is_epoch_current(run_document, work_unit_id, epoch):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"stale worker lease epoch for work unit {work_unit_id!r}",
            "/payload/epoch",
        )
    current_lease = fencing.current_lease(run_document, work_unit_id)
    if current_lease is None or current_lease.get("lease_id") != payload["worker_lease_id"]:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"worker lease id is not current for work unit {work_unit_id!r}",
            "/payload/worker_lease_id",
        )

    merge_path = workspace_root.ai_team / "runs" / "integration-merges" / f"{merge_id}.yaml"
    if merge_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"integration merge {merge_id!r} already exists",
            "/target/id",
        )

    # Document 6 §7.1 — a Work Unit whose ceiling was tightened to forbidden
    # can never merge into the integration branch, no matter what this
    # command's caller claims about conflict resolution or revalidation.
    ceiling = (run_document.get("execution_ceilings_by_work_unit") or {}).get(
        work_unit_id, DEFAULT_EXECUTION_CEILING
    )
    if ceiling["integration_branch_merge"] == "forbidden":
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"integration_branch_merge is forbidden for work unit {work_unit_id!r}",
            "/payload/work_unit_id",
        )

    # Document 6 §9.8 — "mêmes limites de tentative que §9.3": conflict
    # resolution is bounded, never an unbounded retry loop.
    maximum_attempts = run_document.get(
        "maximum_attempts_per_step", DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP
    )
    if attempts >= maximum_attempts:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"conflict resolution budget exhausted for work unit {work_unit_id!r} "
            f"({attempts} attempts, maximum {maximum_attempts})",
            "/payload/conflict_resolution_attempts",
        )

    # Document 6 §9.8 — "revalidation complète après chaque fusion": never optional.
    if not payload["revalidation_passed"]:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "an integration merge cannot be recorded without a passed revalidation",
            "/payload/revalidation_passed",
        )

    now = datetime.now(UTC).isoformat()
    document = {
        "id": merge_id,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "worker_lease_id": payload["worker_lease_id"],
        "epoch": epoch,
        "integration_branch": run_document["integration_branch"],
        "conflict_resolution_attempts": attempts,
        "revalidation_passed": True,
        "revalidation_evidence": payload.get("revalidation_evidence", []),
        "merged_at": now,
    }
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "integration-merge.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(merge_path, document)

    return {
        "affected": [
            {"kind": "integration_merge", "id": merge_id, "work_unit_id": work_unit_id},
        ],
    }, []
