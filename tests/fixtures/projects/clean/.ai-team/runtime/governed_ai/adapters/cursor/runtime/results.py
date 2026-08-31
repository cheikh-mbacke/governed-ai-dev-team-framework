"""RuntimeResult persistence under ``.ai-team/runtime-results/``."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governed_ai.adapters.spi import ExecutionRequest, RuntimeResult

from ..compiler.compile import ADAPTER_ID, ADAPTER_VERSION
from ..compiler.staging import sha256_bytes

RUNTIME_RESULTS_DIR = ".ai-team/runtime-results"
EXECUTION_ID_RE = re.compile(r"^EXE-[A-Za-z0-9-]+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


def runtime_results_dir(project_root: Path) -> Path:
    return project_root / RUNTIME_RESULTS_DIR


def result_path(project_root: Path, execution_id: str) -> Path:
    if not EXECUTION_ID_RE.match(execution_id):
        raise ValueError(f"invalid execution_id: {execution_id}")
    return runtime_results_dir(project_root) / f"{execution_id}.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_runtime_result(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in (
        "protocol_version",
        "execution_id",
        "correlation_id",
        "status",
        "started_at",
        "finished_at",
        "adapter",
        "contract",
        "workspace",
    ):
        if key not in result:
            errors.append(f"missing field: {key}")

    execution_id = result.get("execution_id")
    if not isinstance(execution_id, str) or not EXECUTION_ID_RE.match(execution_id):
        errors.append("execution_id must match EXE-<id>")

    adapter = result.get("adapter")
    if not isinstance(adapter, dict):
        errors.append("adapter must be an object")
    else:
        if adapter.get("id") != ADAPTER_ID:
            errors.append("adapter.id must be cursor")
        if not adapter.get("version"):
            errors.append("adapter.version required")

    contract = result.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract must be an object")
    else:
        for key in ("bundle_version", "role_id", "role_revision", "procedure_id", "procedure_revision"):
            if not contract.get(key):
                errors.append(f"contract.{key} required")

    workspace = result.get("workspace")
    if isinstance(workspace, dict):
        for sha_key in ("base_sha", "result_sha"):
            value = workspace.get(sha_key)
            if value is not None and (not isinstance(value, str) or not SHA40_RE.match(value)):
                errors.append(f"workspace.{sha_key} must be 40-char hex when set")

    artifacts = result.get("artifacts") or []
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        for entry in artifacts:
            if not isinstance(entry, dict):
                errors.append("artifact entry must be an object")
                continue
            digest = entry.get("sha256")
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                errors.append("artifact sha256 required")

    return errors


def build_runtime_result(
    request: ExecutionRequest,
    *,
    status: str = "succeeded",
    summary: str = "Execution recorded without authoritative side effects.",
    checks: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    requested_commands: list[object] | None = None,
    result_sha: str | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    usage: dict[str, Any] | None = None,
) -> RuntimeResult:
    contract = request["contract"]
    started = utc_now_iso()
    finished = utc_now_iso()
    workspace = {
        "base_sha": request.get("base_sha", ""),
        "result_sha": result_sha or request.get("base_sha", ""),
    }
    if workspace["base_sha"] and not SHA40_RE.match(str(workspace["base_sha"])):
        raise ValueError("base_sha must be 40-char hex when provided")
    if workspace["result_sha"] and not SHA40_RE.match(str(workspace["result_sha"])):
        raise ValueError("result_sha must be 40-char hex when provided")

    return RuntimeResult(
        protocol_version=str(request.get("protocol_version", "1.0")),
        execution_id=str(request["execution_id"]),
        correlation_id=str(request.get("correlation_id", "")),
        status=status,  # type: ignore[typeddict-item]
        started_at=started,
        finished_at=finished,
        adapter={"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        contract={
            "bundle_version": str(contract["bundle_version"]),
            "role_id": str(contract["role_id"]),
            "role_revision": str(contract["role_revision"]),
            "procedure_id": str(contract["procedure_id"]),
            "procedure_revision": str(contract["procedure_revision"]),
        },
        workspace=workspace,
        checks=checks or [],
        artifacts=artifacts or [],
        summary=summary,
        limitations=limitations or [],
        requested_commands=requested_commands or [],
        usage=usage or {},
    )


def persist_runtime_result(project_root: Path, result: RuntimeResult) -> Path:
    project_root = project_root.resolve()
    payload = dict(result)
    path = result_path(project_root, str(result["execution_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(body)
    digest = sha256_bytes(body)
    payload["artifacts"] = list(payload.get("artifacts") or []) + [
        {
            "kind": "runtime_result",
            "path": path.relative_to(project_root).as_posix(),
            "sha256": digest,
        }
    ]
    body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(body)
    errors = validate_runtime_result(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return path


def load_runtime_result(project_root: Path, execution_id: str) -> RuntimeResult:
    path = result_path(project_root, execution_id)
    if not path.is_file():
        raise FileNotFoundError(f"runtime result missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("runtime result root must be an object")
    errors = validate_runtime_result(data)
    if errors:
        raise ValueError("; ".join(errors))
    return RuntimeResult(**data)  # type: ignore[misc]
