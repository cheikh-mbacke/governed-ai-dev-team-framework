"""Strict runtime validation of canonical execution structures."""

from __future__ import annotations

import re
from typing import Any

from governed_ai.core.execution_gateway.contracts import (
    MAX_ARTIFACTS,
    MAX_CHECKS,
    MAX_LIMITATIONS,
    MAX_SUMMARY_CHARS,
    SCHEMA_VERSION,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_VALID_STATUSES = frozenset(
    {"succeeded", "failed", "blocked", "cancelled", "timed_out", "rejected"}
)
_VALID_TRUST = frozenset(
    {"agent_reported", "framework_observed", "framework_verified", "human_verified"}
)
_VALID_CHECK_STATUS = frozenset(
    {"passed", "failed", "blocked", "skipped", "timed_out", "unknown"}
)

_REQUIRED_REQUEST = (
    "schema_version",
    "execution_id",
    "run_id",
    "work_unit_id",
    "lease_id",
    "epoch",
    "role_id",
    "procedure_id",
    "base_sha",
    "context_package_hash",
    "contract",
)

_REQUIRED_RESULT = (
    "schema_version",
    "execution_id",
    "run_id",
    "work_unit_id",
    "lease_id",
    "epoch",
    "role_id",
    "procedure_id",
    "status",
    "summary",
    "checks",
    "artifacts",
    "requested_commands",
    "limitations",
    "workspace",
    "usage",
    "provider_metadata",
    "context_package_hash",
)

_REQUIRED_CONTRACT = (
    "schema_version",
    "role_id",
    "procedure_id",
    "effective_scope",
    "required_checks",
    "allowed_shell_commands",
)

_REQUIRED_CAPABILITY = (
    "schema_version",
    "adapter_id",
    "adapter_version",
    "supported_protocol_versions",
    "supported_roles",
    "supported_procedures",
    "isolated_workspace",
    "structured_output",
)


def _safe_int(value: Any, *, path: str, errors: list[StructuredError]) -> int | None:
    if type(value) is not int:
        errors.append(
            StructuredError(
                code="invalid_type",
                message=f"{path} must be an integer",
                path=path,
                details={"value": repr(value)},
            )
        )
        return None
    return value


def _expect_type(
    value: Any,
    expected: type | tuple[type, ...],
    *,
    path: str,
    errors: list[StructuredError],
) -> bool:
    expected_types = expected if isinstance(expected, tuple) else (expected,)
    if type(value) not in expected_types:
        errors.append(
            StructuredError(
                code="invalid_type",
                message=f"{path} has invalid type",
                path=path,
                details={"expected": str(expected), "actual": type(value).__name__},
            )
        )
        return False
    return True


def _expect_nonempty_str(value: Any, *, path: str, errors: list[StructuredError]) -> bool:
    if not _expect_type(value, str, path=path, errors=errors):
        return False
    if not value.strip():
        errors.append(
            StructuredError(
                code="empty_string",
                message=f"{path} must be a non-empty string",
                path=path,
            )
        )
        return False
    return True


def _expect_id(value: Any, *, path: str, errors: list[StructuredError]) -> bool:
    if not _expect_nonempty_str(value, path=path, errors=errors):
        return False
    if not _ID_RE.match(value):
        errors.append(
            StructuredError(
                code="invalid_identifier",
                message=f"{path} is not a valid identifier",
                path=path,
            )
        )
        return False
    return True


def validate_execution_contract(contract: Any, *, path: str = "contract") -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(contract, dict, path=path, errors=errors):
        return errors
    for field in _REQUIRED_CONTRACT:
        if field not in contract:
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {path}.{field} missing",
                    path=f"{path}.{field}",
                )
            )
    version = _safe_int(contract.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(
            StructuredError(
                code="unsupported_schema_version",
                message=f"schema_version must be {SCHEMA_VERSION}",
                path=f"{path}.schema_version",
            )
        )
    for field in ("role_id", "procedure_id"):
        if field in contract:
            _expect_id(contract.get(field), path=f"{path}.{field}", errors=errors)
    for field in ("effective_scope", "required_checks", "allowed_shell_commands", "excluded_paths", "accessible_secrets"):
        if field in contract and contract[field] is not None:
            if not _expect_type(contract[field], list, path=f"{path}.{field}", errors=errors):
                continue
            for index, item in enumerate(contract[field]):
                _expect_nonempty_str(item, path=f"{path}.{field}[{index}]", errors=errors)
    for field in ("contract_id", "bundle_version", "bundle_hash", "role_revision", "procedure_revision"):
        if field in contract:
            _expect_nonempty_str(contract[field], path=f"{path}.{field}", errors=errors)
    if "context_package_hash" in contract:
        digest = contract["context_package_hash"]
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest.lower()):
            errors.append(StructuredError("invalid_sha256", "invalid context package hash", f"{path}.context_package_hash"))
    if "timeout_seconds" in contract:
        value = contract["timeout_seconds"]
        if type(value) not in (int, float) or value <= 0:
            errors.append(StructuredError("invalid_type", "timeout_seconds must be a positive number", f"{path}.timeout_seconds"))
    if "max_artifact_bytes" in contract:
        value = contract["max_artifact_bytes"]
        if type(value) is not int or value < 1:
            errors.append(StructuredError("invalid_type", "max_artifact_bytes must be a positive integer", f"{path}.max_artifact_bytes"))
    return errors


def validate_capability_descriptor(
    descriptor: Any, *, path: str = "capabilities"
) -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(descriptor, dict, path=path, errors=errors):
        return errors
    for field in _REQUIRED_CAPABILITY:
        if field not in descriptor:
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {path}.{field} missing",
                    path=f"{path}.{field}",
                )
            )
    version = _safe_int(descriptor.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(
            StructuredError(
                code="unsupported_schema_version",
                message=f"schema_version must be {SCHEMA_VERSION}",
                path=f"{path}.schema_version",
            )
        )
    for field in ("adapter_id", "adapter_version"):
        if field in descriptor:
            _expect_nonempty_str(descriptor.get(field), path=f"{path}.{field}", errors=errors)
    for field in (
        "supported_protocol_versions",
        "supported_roles",
        "supported_procedures",
    ):
        if field in descriptor:
            if not _expect_type(descriptor[field], list, path=f"{path}.{field}", errors=errors):
                continue
            if field in {"supported_roles", "supported_procedures"} and not descriptor[field]:
                errors.append(
                    StructuredError(
                        code="empty_capability_list",
                        message=f"{path}.{field} must not be empty",
                        path=f"{path}.{field}",
                    )
                )
            for index, item in enumerate(descriptor[field]):
                _expect_nonempty_str(item, path=f"{path}.{field}[{index}]", errors=errors)
    for field in (
        "isolated_workspace",
        "structured_output",
        "cancellation",
        "progress_events",
        "command_enforcement",
        "filesystem_enforcement",
    ):
        if field in descriptor and not isinstance(descriptor[field], bool):
            errors.append(
                StructuredError(
                    code="invalid_type",
                    message=f"{path}.{field} must be a boolean",
                    path=f"{path}.{field}",
                )
            )
    if "maximum_parallelism" in descriptor:
        value = descriptor["maximum_parallelism"]
        if type(value) is not int or value < 1:
            errors.append(
                StructuredError(
                    code="invalid_type",
                    message=f"{path}.maximum_parallelism must be a positive integer",
                    path=f"{path}.maximum_parallelism",
                )
            )
    combinations = descriptor.get("supported_role_procedures")
    if combinations is not None:
        if _expect_type(combinations, list, path=f"{path}.supported_role_procedures", errors=errors):
            for index, pair in enumerate(combinations):
                pair_path = f"{path}.supported_role_procedures[{index}]"
                if type(pair) not in (list, tuple) or len(pair) != 2:
                    errors.append(StructuredError("invalid_type", "role/procedure capability must be a pair", pair_path))
                    continue
                _expect_nonempty_str(pair[0], path=f"{pair_path}[0]", errors=errors)
                _expect_nonempty_str(pair[1], path=f"{pair_path}[1]", errors=errors)
    return errors


def validate_check_result(check: Any, *, path: str) -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(check, dict, path=path, errors=errors):
        return errors
    for field in ("schema_version", "canonical_id", "reported_name", "status", "blocking", "trust_level", "limitations"):
        if field not in check:
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {path}.{field} missing",
                    path=f"{path}.{field}",
                )
            )
    version = _safe_int(check.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(StructuredError("unsupported_schema_version", f"schema_version must be {SCHEMA_VERSION}", f"{path}.schema_version"))
    for field in ("canonical_id", "reported_name"):
        if field in check:
            _expect_nonempty_str(check[field], path=f"{path}.{field}", errors=errors)
    if "status" in check and (type(check["status"]) is not str or check["status"] not in _VALID_CHECK_STATUS):
        errors.append(
            StructuredError(
                code="invalid_enum",
                message=f"invalid check status {check.get('status')!r}",
                path=f"{path}.status",
            )
        )
    if "trust_level" in check and (type(check["trust_level"]) is not str or check["trust_level"] not in _VALID_TRUST):
        errors.append(
            StructuredError(
                code="invalid_enum",
                message=f"invalid trust_level {check.get('trust_level')!r}",
                path=f"{path}.trust_level",
            )
        )
    if "blocking" in check:
        _expect_type(check["blocking"], bool, path=f"{path}.blocking", errors=errors)
    if "limitations" in check and _expect_type(check["limitations"], list, path=f"{path}.limitations", errors=errors):
        for index, value in enumerate(check["limitations"]):
            _expect_type(value, str, path=f"{path}.limitations[{index}]", errors=errors)
    for field in ("exit_code", "duration_ms"):
        if check.get(field) is not None:
            _safe_int(check[field], path=f"{path}.{field}", errors=errors)
    if check.get("transcript_hash") is not None:
        value = check["transcript_hash"]
        if type(value) is not str or not _SHA256_RE.fullmatch(value.lower()):
            errors.append(StructuredError("invalid_sha256", "invalid transcript hash", f"{path}.transcript_hash"))
    return errors


def validate_artifact_evidence(artifact: Any, *, path: str) -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(artifact, dict, path=path, errors=errors):
        return errors
    for field in ("schema_version", "kind", "path", "trust_level"):
        if field not in artifact:
            errors.append(StructuredError("missing_field", f"required field {path}.{field} missing", f"{path}.{field}"))
    version = _safe_int(artifact.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(StructuredError("unsupported_schema_version", f"schema_version must be {SCHEMA_VERSION}", f"{path}.schema_version"))
    if "path" in artifact:
        _expect_nonempty_str(artifact.get("path"), path=f"{path}.path", errors=errors)
    if "kind" in artifact:
        _expect_nonempty_str(artifact.get("kind"), path=f"{path}.kind", errors=errors)
    if "trust_level" in artifact and (type(artifact["trust_level"]) is not str or artifact["trust_level"] not in _VALID_TRUST):
        errors.append(StructuredError("invalid_enum", "invalid artifact trust_level", f"{path}.trust_level"))
    for field in ("agent_reported_sha256", "observed_sha256"):
        digest = artifact.get(field)
        if digest is None or digest == "":
            continue
        if not isinstance(digest, str) or not (
            _SHA256_RE.fullmatch(digest.lower())
            or re.fullmatch(r"[0-9a-fA-F]{64}", digest)
        ):
            errors.append(StructuredError("invalid_sha256", f"{path}.{field} is not a SHA-256 digest", f"{path}.{field}"))
    if artifact.get("size_bytes") is not None:
        size = _safe_int(artifact["size_bytes"], path=f"{path}.size_bytes", errors=errors)
        if size is not None and size < 0:
            errors.append(StructuredError("invalid_value", "size_bytes must be non-negative", f"{path}.size_bytes"))
    return errors


def validate_workspace_result(workspace: Any, *, path: str = "workspace") -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(workspace, dict, path=path, errors=errors):
        return errors
    for field in ("schema_version", "base_sha", "claimed_result_sha", "observed_head_sha", "promoted_sha", "trust_level", "resumable"):
        if field not in workspace:
            errors.append(StructuredError("missing_field", f"required field {path}.{field} missing", f"{path}.{field}"))
    version = _safe_int(workspace.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(StructuredError("unsupported_schema_version", f"schema_version must be {SCHEMA_VERSION}", f"{path}.schema_version"))
    for field in ("base_sha", "claimed_result_sha", "observed_head_sha", "promoted_sha"):
        value = workspace.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value.lower()):
            errors.append(StructuredError("invalid_git_sha", f"{path}.{field} must be a 40-char git SHA", f"{path}.{field}"))
    if "trust_level" in workspace and workspace["trust_level"] not in _VALID_TRUST:
        errors.append(StructuredError("invalid_enum", "invalid workspace trust_level", f"{path}.trust_level"))
    if "resumable" in workspace:
        _expect_type(workspace["resumable"], bool, path=f"{path}.resumable", errors=errors)
    return errors


def validate_evidence_manifest(manifest: Any, *, path: str = "evidence") -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not _expect_type(manifest, dict, path=path, errors=errors):
        return errors
    for field in (
        "schema_version",
        "evidence_id",
        "source",
        "trust_level",
        "producer",
        "run_id",
        "work_unit_id",
        "execution_id",
        "canonical_check_id",
    ):
        if field not in manifest:
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {path}.{field} missing",
                    path=f"{path}.{field}",
                )
            )
    version = _safe_int(manifest.get("schema_version"), path=f"{path}.schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(StructuredError("unsupported_schema_version", f"schema_version must be {SCHEMA_VERSION}", f"{path}.schema_version"))
    for field in ("evidence_id", "source", "producer", "run_id", "work_unit_id", "execution_id", "canonical_check_id"):
        if field in manifest:
            _expect_nonempty_str(manifest[field], path=f"{path}.{field}", errors=errors)
    if manifest.get("trust_level") not in _VALID_TRUST:
        errors.append(
            StructuredError(
                code="invalid_enum",
                message=f"invalid trust_level {manifest.get('trust_level')!r}",
                path=f"{path}.trust_level",
            )
        )
    for field in ("content_hash", "command_digest"):
        value = manifest.get(field)
        if value is not None and (type(value) is not str or not _SHA256_RE.fullmatch(value.lower())):
            errors.append(StructuredError("invalid_sha256", f"invalid {field}", f"{path}.{field}"))
    return errors


def validate_execution_request(request: dict[str, Any]) -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not isinstance(request, dict):
        return [
            StructuredError(
                code="invalid_type",
                message="ExecutionRequest must be an object",
                path="$",
            )
        ]
    version = _safe_int(request.get("schema_version"), path="schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(
            StructuredError(
                code="unsupported_schema_version",
                message=f"schema_version must be {SCHEMA_VERSION}",
                path="schema_version",
            )
        )
    for field in _REQUIRED_REQUEST:
        if request.get(field) in (None, ""):
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {field} missing",
                    path=field,
                )
            )
    for field in ("execution_id", "run_id", "work_unit_id", "lease_id", "role_id", "procedure_id"):
        if field in request and request[field] not in (None, ""):
            _expect_id(request[field], path=field, errors=errors)
    epoch = _safe_int(request.get("epoch"), path="epoch", errors=errors)
    if epoch is not None and epoch < 1:
        errors.append(
            StructuredError(
                code="invalid_epoch",
                message="epoch must be a positive integer",
                path="epoch",
            )
        )
    base_sha = request.get("base_sha")
    if base_sha is not None and (
        type(base_sha) is not str or not _GIT_SHA_RE.fullmatch(base_sha.lower())
    ):
        errors.append(
            StructuredError(
                code="invalid_git_sha",
                message="base_sha must be a 40-char git SHA",
                path="base_sha",
            )
        )
    ctx = request.get("context_package_hash")
    if ctx is not None and (
        type(ctx) is not str or not _SHA256_RE.fullmatch(ctx.lower())
    ):
        errors.append(
            StructuredError(
                code="invalid_sha256",
                message="context_package_hash must be sha256:<64 hex>",
                path="context_package_hash",
            )
        )
    if "contract" in request:
        errors.extend(validate_execution_contract(request.get("contract")))
    return errors


def validate_execution_result(result: dict[str, Any]) -> list[StructuredError]:
    errors: list[StructuredError] = []
    if not isinstance(result, dict):
        return [
            StructuredError(
                code="invalid_type",
                message="ExecutionResult must be an object",
                path="$",
            )
        ]
    version = _safe_int(result.get("schema_version"), path="schema_version", errors=errors)
    if version is not None and version != SCHEMA_VERSION:
        errors.append(
            StructuredError(
                code="unsupported_schema_version",
                message=f"schema_version must be {SCHEMA_VERSION}",
                path="schema_version",
            )
        )
    for field in _REQUIRED_RESULT:
        if field not in result:
            errors.append(
                StructuredError(
                    code="missing_field",
                    message=f"required field {field} missing",
                    path=field,
                )
            )
    for field in ("execution_id", "run_id", "work_unit_id", "lease_id", "role_id", "procedure_id"):
        if field in result and result[field] not in (None, ""):
            _expect_id(result[field], path=field, errors=errors)
    epoch = _safe_int(result.get("epoch"), path="epoch", errors=errors)
    if epoch is not None and epoch < 1:
        errors.append(
            StructuredError(
                code="invalid_epoch",
                message="epoch must be a positive integer",
                path="epoch",
            )
        )
    status = result.get("status")
    if status is not None and (type(status) is not str or status not in _VALID_STATUSES):
        errors.append(
            StructuredError(
                code="invalid_enum",
                message=f"invalid status {status!r}",
                path="status",
            )
        )
    summary = result.get("summary")
    if summary is not None:
        if _expect_nonempty_str(summary, path="summary", errors=errors) and len(summary) > MAX_SUMMARY_CHARS:
            errors.append(
                StructuredError(
                    code="summary_too_large",
                    message=f"summary exceeds {MAX_SUMMARY_CHARS} chars",
                    path="summary",
                )
            )
    checks = result.get("checks")
    if checks is not None:
        if _expect_type(checks, list, path="checks", errors=errors):
            if len(checks) > MAX_CHECKS:
                errors.append(
                    StructuredError(
                        code="too_many_checks",
                        message=f"checks exceed {MAX_CHECKS}",
                        path="checks",
                    )
                )
            for index, check in enumerate(checks):
                errors.extend(validate_check_result(check, path=f"checks[{index}]"))
    artifacts = result.get("artifacts")
    if artifacts is not None:
        if _expect_type(artifacts, list, path="artifacts", errors=errors):
            if len(artifacts) > MAX_ARTIFACTS:
                errors.append(
                    StructuredError(
                        code="too_many_artifacts",
                        message=f"artifacts exceed {MAX_ARTIFACTS}",
                        path="artifacts",
                    )
                )
            for index, artifact in enumerate(artifacts):
                errors.extend(validate_artifact_evidence(artifact, path=f"artifacts[{index}]"))
    limitations = result.get("limitations")
    if limitations is not None:
        if _expect_type(limitations, list, path="limitations", errors=errors):
            if len(limitations) > MAX_LIMITATIONS:
                errors.append(
                    StructuredError(
                        code="too_many_limitations",
                        message=f"limitations exceed {MAX_LIMITATIONS}",
                        path="limitations",
                    )
                )
            for index, limitation in enumerate(limitations):
                _expect_type(limitation, str, path=f"limitations[{index}]", errors=errors)
    if "requested_commands" in result and result["requested_commands"] is not None:
        if _expect_type(result["requested_commands"], list, path="requested_commands", errors=errors):
            for index, command in enumerate(result["requested_commands"]):
                command_path = f"requested_commands[{index}]"
                if type(command) is str:
                    _expect_nonempty_str(command, path=command_path, errors=errors)
                elif type(command) is dict:
                    if not command.get("command") and not command.get("argv"):
                        errors.append(StructuredError("missing_field", "command or argv is required", command_path))
                    if "argv" in command:
                        argv = command["argv"]
                        if _expect_type(argv, list, path=f"{command_path}.argv", errors=errors):
                            if not argv:
                                errors.append(StructuredError("empty_list", "argv must not be empty", f"{command_path}.argv"))
                            for part_index, part in enumerate(argv):
                                _expect_nonempty_str(part, path=f"{command_path}.argv[{part_index}]", errors=errors)
                else:
                    errors.append(StructuredError("invalid_type", "requested command must be string or object", command_path))
    if "usage" in result and result["usage"] is not None:
        _expect_type(result["usage"], dict, path="usage", errors=errors)
    if "provider_metadata" in result and result["provider_metadata"] is not None:
        _expect_type(result["provider_metadata"], dict, path="provider_metadata", errors=errors)
    if "workspace" in result:
        errors.extend(validate_workspace_result(result.get("workspace")))
    ctx = result.get("context_package_hash")
    if ctx is not None and (
        type(ctx) is not str or not _SHA256_RE.fullmatch(ctx.lower())
    ):
        errors.append(
            StructuredError(
                code="invalid_sha256",
                message="context_package_hash must be sha256:<64 hex>",
                path="context_package_hash",
            )
        )
    return errors


def require_valid_request(request: dict[str, Any]) -> None:
    errors = validate_execution_request(request)
    if errors:
        raise ExecutionGatewayError(errors[0])


def require_valid_result(result: dict[str, Any]) -> None:
    errors = validate_execution_result(result)
    if errors:
        raise ExecutionGatewayError(errors[0])


def require_valid_capabilities(descriptor: dict[str, Any]) -> None:
    errors = validate_capability_descriptor(descriptor)
    if errors:
        raise ExecutionGatewayError(errors[0])


def assert_identity_match(request: dict[str, Any], result: dict[str, Any]) -> None:
    for field in (
        "execution_id",
        "run_id",
        "work_unit_id",
        "lease_id",
        "epoch",
        "role_id",
        "procedure_id",
    ):
        expected = request.get(field)
        actual = result.get(field)
        if field == "epoch":
            left = _safe_int(actual, path=field, errors=[])
            right = _safe_int(expected, path=field, errors=[])
            if left is None or right is None or left != right:
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


def assert_agent_status_promotable(status: str) -> None:
    """Only an agent ``succeeded`` status may proceed to promotion."""
    if status != "succeeded":
        raise ExecutionGatewayError(
            StructuredError(
                code="agent_status_not_succeeded",
                message=(
                    f"refusing to promote agent status {status!r}; "
                    "only succeeded may be accepted"
                ),
                path="status",
                details={"status": status},
            )
        )
