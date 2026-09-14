"""LegacyExecutionResultAdapter — isolated compatibility for older agent outputs."""

from __future__ import annotations

from typing import Any

from governed_ai.core.execution_gateway.check_registry import normalize_check_name
from governed_ai.core.execution_gateway.contracts import (
    SCHEMA_VERSION,
    ArtifactEvidence,
    CheckResult,
    ExecutionRequest,
    ExecutionResult,
    WorkspaceResult,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _identity_epoch(value: Any, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExecutionGatewayError(
            StructuredError(
                code="invalid_type",
                message=f"{path} must be an integer",
                path=path,
                details={"actual": type(value).__name__},
            )
        )
    return value


class LegacyExecutionResultAdapter:
    """Translate RuntimeResult / prose-handoff shapes into canonical ExecutionResult.

    This is the ONLY compatibility path for non-canonical agent outputs.
    """

    def adapt(
        self,
        raw: dict[str, Any],
        *,
        request: ExecutionRequest | dict[str, Any],
    ) -> ExecutionResult:
        if not isinstance(raw, dict):
            raise ExecutionGatewayError(
                StructuredError(
                    code="invalid_execution_result",
                    message="legacy result must be an object",
                    path="$",
                )
            )

        # Prefer already-canonical payloads, but still normalize incomplete checks.
        if (
            type(raw.get("schema_version")) is int
            and raw["schema_version"] >= 1
            and raw.get("run_id")
            and raw.get("checks") is not None
        ):
            normalized = dict(raw)
            checks_fixed: list[CheckResult] = []
            for item in normalized.get("checks") or []:
                if not isinstance(item, dict):
                    checks_fixed.append(item)  # type: ignore[arg-type]
                    continue
                if item.get("canonical_id"):
                    normalized_check = dict(item)
                    normalized_check.setdefault("schema_version", SCHEMA_VERSION)
                    normalized_check.setdefault(
                        "reported_name", normalized_check.get("canonical_id")
                    )
                    normalized_check.setdefault("blocking", True)
                    normalized_check.setdefault("trust_level", "agent_reported")
                    normalized_check.setdefault("limitations", [])
                    checks_fixed.append(normalized_check)  # type: ignore[arg-type]
                    continue
                reported = str(item.get("name") or item.get("reported_name") or "")
                canonical = normalize_check_name(reported) or reported
                checks_fixed.append(
                    CheckResult(
                        schema_version=SCHEMA_VERSION,
                        canonical_id=canonical,
                        reported_name=reported or canonical,
                        status=str(item.get("status") or "unknown"),
                        blocking=bool(item.get("blocking", True)),
                        trust_level=item.get("trust_level") or "agent_reported",  # type: ignore[typeddict-item]
                        evidence_ref=item.get("evidence_ref"),
                        limitations=list(item.get("limitations") or []),
                    )
                )
            normalized["checks"] = checks_fixed
            artifacts_fixed: list[ArtifactEvidence] = []
            for item in normalized.get("artifacts") or []:
                if not isinstance(item, dict):
                    artifacts_fixed.append(item)  # type: ignore[arg-type]
                    continue
                normalized_artifact = dict(item)
                normalized_artifact.setdefault("schema_version", SCHEMA_VERSION)
                normalized_artifact.setdefault("kind", "file")
                normalized_artifact.setdefault("trust_level", "agent_reported")
                artifacts_fixed.append(normalized_artifact)  # type: ignore[arg-type]
            normalized["artifacts"] = artifacts_fixed
            workspace = normalized.get("workspace")
            if isinstance(workspace, dict):
                normalized_workspace = dict(workspace)
                normalized_workspace.setdefault("schema_version", SCHEMA_VERSION)
                normalized_workspace.setdefault("base_sha", request.get("base_sha"))
                normalized_workspace.setdefault(
                    "claimed_result_sha", normalized_workspace.get("result_sha")
                )
                normalized_workspace.setdefault("observed_head_sha", None)
                normalized_workspace.setdefault("promoted_sha", None)
                normalized_workspace.setdefault("trust_level", "agent_reported")
                normalized_workspace.setdefault("resumable", False)
                normalized["workspace"] = normalized_workspace
            normalized.setdefault("requested_commands", [])
            normalized.setdefault("limitations", [])
            normalized.setdefault("usage", {})
            normalized.setdefault("provider_metadata", normalized.get("provider") or {})
            return self._validate_identity(normalized, request)  # type: ignore[return-value]

        # Refuse identity spoofing even on legacy shapes when fields are present.
        for field in ("execution_id", "run_id", "work_unit_id", "lease_id", "epoch", "role_id", "procedure_id"):
            if field not in raw:
                continue
            expected = request.get(field)
            actual = raw.get(field)
            if expected in (None, ""):
                continue
            if field == "epoch":
                if _identity_epoch(actual, path=field) != _identity_epoch(
                    expected, path=f"request.{field}"
                ):
                    raise ExecutionGatewayError(
                        StructuredError(
                            code="identity_mismatch",
                            message=f"result.{field} does not match request",
                            path=field,
                            details={"expected": expected, "actual": actual},
                        )
                    )
            elif str(actual) != str(expected):
                raise ExecutionGatewayError(
                    StructuredError(
                        code="identity_mismatch",
                        message=f"result.{field} does not match request",
                        path=field,
                        details={"expected": expected, "actual": actual},
                    )
                )

        workspace = _as_dict(raw.get("workspace"))
        contract = _as_dict(raw.get("contract"))
        checks_in = raw.get("checks") or []
        artifacts_in = raw.get("artifacts") or []

        checks: list[CheckResult] = []
        for item in checks_in:
            if not isinstance(item, dict):
                continue
            reported = str(item.get("name") or item.get("canonical_id") or "")
            canonical = normalize_check_name(reported) or reported
            checks.append(
                CheckResult(
                    schema_version=SCHEMA_VERSION,
                    canonical_id=canonical,
                    reported_name=reported,
                    status=str(item.get("status") or "unknown"),
                    blocking=True,
                    trust_level="agent_reported",
                    evidence_ref=item.get("evidence_ref"),
                    limitations=list(item.get("limitations") or []),
                )
            )

        artifacts: list[ArtifactEvidence] = []
        for item in artifacts_in:
            if not isinstance(item, dict):
                continue
            artifacts.append(
                ArtifactEvidence(
                    schema_version=SCHEMA_VERSION,
                    kind=str(item.get("kind") or "file"),
                    path=str(item.get("path") or ""),
                    agent_reported_sha256=item.get("sha256"),
                    observed_sha256=None,
                    trust_level="agent_reported",
                )
            )

        result: ExecutionResult = {
            "schema_version": SCHEMA_VERSION,
            "execution_id": str(raw.get("execution_id") or request.get("execution_id") or ""),
            "run_id": str(request.get("run_id") or ""),
            "work_unit_id": str(request.get("work_unit_id") or ""),
            "lease_id": str(request.get("lease_id") or ""),
            "epoch": int(request.get("epoch") or 0),
            "role_id": str(
                contract.get("role_id") or request.get("role_id") or ""
            ),
            "procedure_id": str(
                contract.get("procedure_id") or request.get("procedure_id") or ""
            ),
            "status": str(raw.get("status") or "failed"),  # type: ignore[typeddict-item]
            "summary": str(raw.get("summary") or "")[:8000],
            "checks": checks,
            "artifacts": artifacts,
            "requested_commands": list(raw.get("requested_commands") or []),
            "limitations": list(raw.get("limitations") or []),
            "workspace": WorkspaceResult(
                schema_version=SCHEMA_VERSION,
                base_sha=str(workspace.get("base_sha") or request.get("base_sha") or ""),
                claimed_result_sha=workspace.get("result_sha"),
                observed_head_sha=None,
                promoted_sha=None,
                trust_level="agent_reported",
                resumable=False,
            ),
            "usage": dict(raw.get("usage") or {}),
            "provider_metadata": dict(raw.get("provider") or raw.get("provider_metadata") or {}),
            "context_package_hash": str(request.get("context_package_hash") or ""),
            "errors": [],
        }
        return self._validate_identity(result, request)

    def _validate_identity(
        self,
        result: dict[str, Any],
        request: ExecutionRequest | dict[str, Any],
    ) -> ExecutionResult:
        fields = (
            "execution_id",
            "run_id",
            "work_unit_id",
            "lease_id",
            "epoch",
            "role_id",
            "procedure_id",
        )
        for field in fields:
            expected = request.get(field)
            actual = result.get(field)
            if expected is None or expected == "":
                continue
            if field == "epoch":
                if _identity_epoch(actual, path=field) != _identity_epoch(
                    expected, path=f"request.{field}"
                ):
                    raise ExecutionGatewayError(
                        StructuredError(
                            code="identity_mismatch",
                            message=f"result.{field} does not match request",
                            path=field,
                            details={"expected": expected, "actual": actual},
                        )
                    )
            elif str(actual) != str(expected):
                raise ExecutionGatewayError(
                    StructuredError(
                        code="identity_mismatch",
                        message=f"result.{field} does not match request",
                        path=field,
                        details={"expected": expected, "actual": actual},
                    )
                )
        # Force request identity onto the canonical result (agent cannot redefine).
        for field in fields:
            if request.get(field) is not None and request.get(field) != "":
                result[field] = request[field]
        result["schema_version"] = SCHEMA_VERSION
        return result  # type: ignore[return-value]
