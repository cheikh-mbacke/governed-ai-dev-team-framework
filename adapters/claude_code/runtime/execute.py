"""Claude Code adapter execute/collect — records RuntimeResult without Core mutations.

v1 (pilot) scope: always stub. Unlike ``adapters/cursor/runtime/execute.py``,
there is no real-launch branch here yet — the exact ``claude -p
--output-format json`` output contract has not been verified against a real
subprocess (Cursor's equivalent contract *was* probed manually before
``agent_cli.py`` was written; see its docstring). Wiring a real
``claude_cli.py`` is an explicit follow-up increment, not attempted here.
"""

from __future__ import annotations

from pathlib import Path

from governed_ai.adapters.spi import ExecutionRequest, RuntimeResult

from .results import build_runtime_result, load_runtime_result, persist_runtime_result


def execute_runtime(project_root: Path, request: ExecutionRequest) -> RuntimeResult:
    """Record a terminal RuntimeResult; never mutates authoritative project state."""
    _validate_request(request)
    result = build_runtime_result(
        request,
        status="blocked",
        summary="Claude Code runtime harness recorded execution; no Command Gateway commands emitted.",
        limitations=[
            "Native Claude Code launch not implemented in this increment "
            "(pilot skeleton — see plan snug-knitting-catmull, follow-up section).",
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
