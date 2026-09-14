"""Compiled context package hashing for execution requests."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from governed_ai.core.execution_gateway.contracts import SCHEMA_VERSION
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError


def _stable_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_context_package(package: dict[str, Any]) -> str:
    """Hash the canonical bytes of a context package (excluding its own hash field)."""
    material = {key: value for key, value in package.items() if key != "context_package_hash"}
    digest = hashlib.sha256(_stable_dumps(material).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compile_context_package(
    *,
    contract: dict[str, Any],
    role_id: str,
    procedure_id: str,
    work_unit: dict[str, Any],
    acceptance_criteria: list[Any],
    required_checks: list[str],
    effective_scope: dict[str, Any],
    constraints: dict[str, Any] | None = None,
    useful_files: list[str] | None = None,
    decisions: list[Any] | None = None,
    time_budget: dict[str, Any] | None = None,
    result_format: dict[str, Any] | None = None,
    design_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an immutable context package then hash its final canonical bytes.

    The contract embedded in the package is a deep copy so later mutations of
    the caller's contract dict cannot invalidate the hash.
    """
    contract_copy = copy.deepcopy(contract)
    package: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract": contract_copy,
        "role_id": role_id,
        "procedure_id": procedure_id,
        "work_unit": {
            "id": work_unit.get("id"),
            "title": work_unit.get("title"),
            "objective": work_unit.get("objective"),
            "scope": copy.deepcopy(work_unit.get("scope")),
            "zone": copy.deepcopy(work_unit.get("zone")),
            "design_binding": copy.deepcopy(work_unit.get("design_binding")),
        },
        "acceptance_criteria": copy.deepcopy(acceptance_criteria),
        "required_checks": list(required_checks),
        "effective_scope": copy.deepcopy(effective_scope),
        "constraints": copy.deepcopy(constraints or {}),
        "useful_files": list(useful_files or []),
        "decisions": copy.deepcopy(decisions or []),
        "time_budget": copy.deepcopy(time_budget or {}),
        "result_format": copy.deepcopy(
            result_format
            or {
                "type": "ExecutionResult",
                "schema_version": SCHEMA_VERSION,
            }
        ),
    }
    if design_context is not None:
        package["design"] = copy.deepcopy(design_context)
    package["context_package_hash"] = hash_context_package(package)
    return package


def assert_context_hash(result_hash: str | None, expected_hash: str) -> None:
    if not expected_hash:
        raise ExecutionGatewayError(
            StructuredError(
                code="context_hash_mismatch",
                message="compiled request is missing context_package_hash",
                path="context_package_hash",
            )
        )
    if not result_hash or str(result_hash) != str(expected_hash):
        raise ExecutionGatewayError(
            StructuredError(
                code="context_hash_mismatch",
                message="result context_package_hash does not match compiled request context",
                path="context_package_hash",
                details={"expected": expected_hash, "actual": result_hash},
            )
        )


def assert_package_hash_matches(package: dict[str, Any], expected_hash: str) -> None:
    """Recalculate the hash of a transmitted package and compare."""
    observed = hash_context_package(package)
    if observed != expected_hash:
        raise ExecutionGatewayError(
            StructuredError(
                code="context_hash_mismatch",
                message="transmitted context package hash does not match canonical recalculation",
                path="context_package_hash",
                details={"expected": expected_hash, "recalculated": observed},
            )
        )
