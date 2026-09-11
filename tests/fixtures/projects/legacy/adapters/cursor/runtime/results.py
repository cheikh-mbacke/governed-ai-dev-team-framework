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
FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)

HANDOFF_SUMMARY_MAX = 4000
HANDOFF_DIAGNOSTIC_MAX = 2000


def runtime_results_dir(project_root: Path) -> Path:
    return project_root / RUNTIME_RESULTS_DIR


def result_path(project_root: Path, execution_id: str) -> Path:
    if not EXECUTION_ID_RE.match(execution_id):
        raise ValueError(f"invalid execution_id: {execution_id}")
    return runtime_results_dir(project_root) / f"{execution_id}.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_conforming_governed_handoff(candidate: Any) -> bool:
    """Return True when ``candidate`` matches the governed handoff contract."""
    if not isinstance(candidate, dict):
        return False
    if not isinstance(candidate.get("summary"), str):
        return False
    if not isinstance(candidate.get("checks"), list):
        return False
    if not isinstance(candidate.get("artifacts"), list):
        return False
    if "requested_commands" in candidate and not isinstance(
        candidate.get("requested_commands"), list
    ):
        return False
    if "usage" in candidate and not isinstance(candidate.get("usage"), dict):
        return False
    for check in candidate["checks"]:
        if not isinstance(check, dict):
            return False
        if not isinstance(check.get("name"), str):
            return False
        if not isinstance(check.get("status"), str):
            return False
    for artifact in candidate["artifacts"]:
        if not isinstance(artifact, dict):
            return False
    return True


def _coerce_handoff(candidate: dict[str, Any]) -> dict[str, Any]:
    handoff = {
        "summary": str(candidate["summary"])[:HANDOFF_SUMMARY_MAX],
        "checks": list(candidate.get("checks") or []),
        "artifacts": list(candidate.get("artifacts") or []),
        "requested_commands": list(candidate.get("requested_commands") or []),
        "usage": dict(candidate.get("usage") or {}),
    }
    return handoff


def _normalize_handoff(handoff: dict[str, Any]) -> str:
    return json.dumps(_coerce_handoff(handoff), sort_keys=True, ensure_ascii=False, default=str)


def _iter_json_values(text: str) -> list[Any]:
    """Collect complete JSON values from text without regex-only nested parsing."""
    values: list[Any] = []
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] not in "{[":
            index += 1
        if index >= length:
            break
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        values.append(value)
        index = max(end, index + 1)
    return values


def _candidate_texts(result_text: str) -> list[str]:
    texts = [result_text]
    for match in FENCED_JSON_RE.finditer(result_text):
        fenced = match.group(1).strip()
        if fenced:
            texts.append(fenced)
    return texts


def extract_governed_handoff(result_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Extract a governed handoff from agent result text.

    Strategy:
    1. accept an exact JSON object when the whole text is that object;
    2. otherwise scan for complete JSON values (including fenced ``json`` blocks);
    3. keep only objects that conform to the handoff contract;
    4. if several conforming candidates disagree, fail explicitly;
    5. otherwise return the last conforming candidate.

    Returns ``(handoff, diagnostic)`` where diagnostic is set on failure and is
    size-bounded.
    """
    text = (result_text or "").strip()
    if not text:
        return None, "agent result was empty"

    try:
        exact = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        exact = None
    if is_conforming_governed_handoff(exact):
        return _coerce_handoff(exact), None

    conforming: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fragment in _candidate_texts(text):
        for value in _iter_json_values(fragment):
            if not is_conforming_governed_handoff(value):
                continue
            coerced = _coerce_handoff(value)
            normalized = _normalize_handoff(coerced)
            if normalized in seen:
                continue
            seen.add(normalized)
            conforming.append(coerced)

    if not conforming:
        diagnostic = text[:HANDOFF_DIAGNOSTIC_MAX]
        return None, (
            "agent result was not the required governed JSON handoff; "
            f"diagnostic excerpt: {diagnostic}"
        )[:HANDOFF_DIAGNOSTIC_MAX]

    if len(conforming) > 1:
        signatures = {_normalize_handoff(item) for item in conforming}
        if len(signatures) > 1:
            return None, (
                f"ambiguous governed JSON handoff: {len(conforming)} contradictory candidates"
            )

    return conforming[-1], None


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
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_ms: int | None = None,
    provider: dict[str, Any] | None = None,
) -> RuntimeResult:
    contract = request["contract"]
    started = started_at or utc_now_iso()
    finished = finished_at or utc_now_iso()
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
        duration_ms=max(0, int(duration_ms or 0)),
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
        provider={key: value for key, value in (provider or {}).items() if value is not None},
    )


def persist_runtime_result(project_root: Path, result: RuntimeResult) -> Path:
    project_root = project_root.resolve()
    payload = dict(result)
    # A file cannot truthfully contain its own final digest.  Runtime-result
    # artifact metadata is therefore materialized by ``load_runtime_result``
    # after hashing the persisted bytes, rather than embedded in those bytes.
    payload["artifacts"] = [
        item for item in payload.get("artifacts", []) if item.get("kind") != "runtime_result"
    ]
    path = result_path(project_root, str(result["execution_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
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
    body = path.read_bytes()
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise TypeError("runtime result root must be an object")
    errors = validate_runtime_result(data)
    if errors:
        raise ValueError("; ".join(errors))
    data["artifacts"] = list(data.get("artifacts") or []) + [
        {
            "kind": "runtime_result",
            "path": path.relative_to(project_root.resolve()).as_posix(),
            "sha256": sha256_bytes(body),
        }
    ]
    return RuntimeResult(**data)  # type: ignore[misc]
