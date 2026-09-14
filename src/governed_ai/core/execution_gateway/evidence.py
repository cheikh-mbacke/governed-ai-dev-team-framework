"""Evidence provenance — never trust agent-declared hashes alone."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Literal

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.execution_gateway.contracts import (
    SCHEMA_VERSION,
    ArtifactEvidence,
    TrustLevel,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.persistence.atomic import atomic_write_text

TrustLevelName = Literal[
    "agent_reported",
    "framework_observed",
    "framework_verified",
    "human_verified",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def normalize_digest(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text.startswith("sha256:"):
        return text
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return f"sha256:{text}"
    return text


def verify_artifact(
    workspace_root: Path,
    *,
    path: str,
    agent_reported_sha256: str | None,
    max_bytes: int,
) -> ArtifactEvidence:
    """Recalculate artifact hash; refuse missing/oversized/tampered files."""
    rel = path.replace("\\", "/").lstrip("/")
    if ".." in Path(rel).parts:
        raise ExecutionGatewayError(
            StructuredError(
                code="forbidden_path_traversal",
                message=f"artifact path escapes workspace: {path}",
                path="artifacts.path",
            )
        )
    absolute = (workspace_root / rel).resolve()
    try:
        absolute.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="absolute_path_outside_workspace",
                message=f"artifact path outside workspace: {path}",
                path="artifacts.path",
            )
        ) from exc
    if not absolute.is_file():
        raise ExecutionGatewayError(
            StructuredError(
                code="artifact_missing",
                message=f"artifact not found: {rel}",
                path="artifacts.path",
            )
        )
    size = absolute.stat().st_size
    if size > max_bytes:
        raise ExecutionGatewayError(
            StructuredError(
                code="artifact_too_large",
                message=f"artifact exceeds max size ({size} > {max_bytes})",
                path="artifacts.path",
                details={"size_bytes": size, "max_bytes": max_bytes},
            )
        )
    observed = sha256_file(absolute)
    reported = normalize_digest(agent_reported_sha256)
    trust: TrustLevel = "framework_verified"
    if reported and reported != observed:
        raise ExecutionGatewayError(
            StructuredError(
                code="artifact_hash_mismatch",
                message="agent-reported artifact hash does not match framework recalculation",
                path="artifacts.sha256",
                details={"reported": reported, "observed": observed, "path": rel},
            )
        )
    if not reported:
        trust = "framework_observed"
    return ArtifactEvidence(
        schema_version=SCHEMA_VERSION,
        kind="file",
        path=rel,
        agent_reported_sha256=reported,
        observed_sha256=observed,
        trust_level=trust,
        size_bytes=size,
    )


def build_evidence_manifest(
    *,
    source: str,
    trust_level: TrustLevelName,
    producer: str,
    verifier: str | None,
    content_hash: str | None,
    artifact_path: str | None,
    run_id: str,
    work_unit_id: str,
    execution_id: str,
    canonical_check_id: str,
    command_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": f"EVD-{uuid.uuid4().hex[:12]}",
        "source": source,
        "trust_level": trust_level,
        "producer": producer,
        "verifier": verifier,
        "created_at": datetime.now(UTC).isoformat(),
        "content_hash": content_hash,
        "command_digest": command_digest,
        "artifact_path": artifact_path,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "execution_id": execution_id,
        "canonical_check_id": canonical_check_id,
    }


def persist_evidence_manifest(ai_team: Path, manifest: dict[str, Any]) -> Path:
    from governed_ai.core.execution_gateway.validation import validate_evidence_manifest

    errors = validate_evidence_manifest(manifest)
    if errors:
        raise ExecutionGatewayError(errors[0])
    evidence_dir = ai_team / "evidence" / str(manifest.get("work_unit_id") or "_gateway")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{manifest['evidence_id']}.json"
    atomic_write_text(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def assert_blocking_check_trust(check: dict[str, Any], *, can_verify: bool) -> None:
    """A blocking check cannot be satisfied by agent_reported alone when verifiable."""
    if not check.get("blocking", True):
        return
    trust = check.get("trust_level") or "agent_reported"
    if can_verify and trust == "agent_reported":
        raise ExecutionGatewayError(
            StructuredError(
                code="insufficient_evidence_trust",
                message=(
                    f"blocking check {check.get('canonical_id')!r} is only agent_reported; "
                    "independent verification required"
                ),
                path="checks.trust_level",
            )
        )
