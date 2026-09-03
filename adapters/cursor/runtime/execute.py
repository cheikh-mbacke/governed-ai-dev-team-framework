"""Cursor adapter execute/collect — records RuntimeResult without Core mutations."""

from __future__ import annotations

from pathlib import Path

from governed_ai.adapters.spi import ExecutionRequest, RuntimeResult

from .agent_cli import invoke_agent_cli, is_real_agent_launch_enabled
from .results import (
    build_runtime_result,
    load_runtime_result,
    persist_runtime_result,
)


def execute_runtime(project_root: Path, request: ExecutionRequest) -> RuntimeResult:
    """Record a terminal RuntimeResult; never mutates authoritative project state.

    Real Cursor agent launch (`agent_cli.invoke_agent_cli`) is opt-in via the
    `GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH` environment variable — real
    invocation costs API credits and can run arbitrary shell/write tool
    calls, so it must never trigger silently just because a caller (e.g. the
    existing test suite) calls this function. Without that opt-in, behavior
    is unchanged from the original WU-P4-RUNTIME harness stub.
    """
    _validate_request(request)
    if is_real_agent_launch_enabled():
        outcome = invoke_agent_cli(project_root, request)
        result = build_runtime_result(
            request,
            status=outcome.status,
            summary=outcome.summary,
            limitations=outcome.limitations,
            checks=outcome.checks,
            artifacts=outcome.artifacts,
            requested_commands=outcome.requested_commands,
            usage=outcome.usage,
            result_sha=outcome.result_sha,
            started_at=outcome.started_at,
            finished_at=outcome.finished_at,
            duration_ms=outcome.duration_ms,
            provider={
                "session_id": outcome.provider_session_id,
                "request_id": outcome.provider_request_id,
                "model": request.get("model"),
            },
        )
    else:
        result = build_runtime_result(
            request,
            status="blocked",
            summary="Cursor runtime harness recorded execution; no Command Gateway commands emitted.",
            limitations=[
                (
                    "Native Cursor agent launch not enabled "
                    "(set GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1 to use the real agent_cli path)."
                )
            ],
            requested_commands=[],
        )
    persist_runtime_result(project_root, result)
    return load_runtime_result(project_root, str(request["execution_id"]))


def collect_runtime_result(project_root: Path, execution_id: str) -> RuntimeResult:
    return load_runtime_result(project_root, execution_id)


def _validate_request(request: ExecutionRequest) -> None:
    execution_id = request.get("execution_id")
    if not execution_id:
        raise ValueError("execution_id required")
    contract = request.get("contract")
    if not isinstance(contract, dict):
        raise TypeError("contract required")
    for key in ("bundle_version", "role_id", "role_revision", "procedure_id", "procedure_revision"):
        if not contract.get(key):
            raise ValueError(f"contract.{key} required")
