"""governed_ai.adapters.common.results — shared RuntimeResult handling."""

from __future__ import annotations

from governed_ai.adapters.common.results import (
    build_runtime_result,
    extract_governed_handoff,
    is_conforming_governed_handoff,
    validate_runtime_result,
)
from governed_ai.adapters.spi import ExecutionRequest

BASE_SHA = "a" * 40


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id="EXE-TEST-1",
        correlation_id="COR-TEST-1",
        contract={
            "bundle_version": "1.0.0",
            "role_id": "backend-developer",
            "role_revision": "1.0.0",
            "procedure_id": "implement-work-unit",
            "procedure_revision": "1.0.0",
        },
        base_sha=BASE_SHA,
    )


def test_build_runtime_result_stamps_given_adapter_identity() -> None:
    result = build_runtime_result(_request(), adapter_id="claude-code", adapter_version="0.1.0")
    assert result["adapter"] == {"id": "claude-code", "version": "0.1.0"}
    assert validate_runtime_result(dict(result), expected_adapter_id="claude-code") == []


def test_validate_runtime_result_rejects_mismatched_expected_adapter_id() -> None:
    result = build_runtime_result(_request(), adapter_id="claude-code", adapter_version="0.1.0")
    errors = validate_runtime_result(dict(result), expected_adapter_id="cursor")
    assert any("adapter.id must be cursor" in e for e in errors)


def test_validate_runtime_result_without_expected_adapter_id_accepts_any_id() -> None:
    result = build_runtime_result(_request(), adapter_id="claude-code", adapter_version="0.1.0")
    assert validate_runtime_result(dict(result)) == []


def test_is_conforming_governed_handoff_requires_summary_checks_artifacts() -> None:
    assert is_conforming_governed_handoff({"summary": "ok", "checks": [], "artifacts": []})
    assert not is_conforming_governed_handoff({"summary": "ok"})
    assert not is_conforming_governed_handoff("not a dict")


def test_extract_governed_handoff_parses_exact_json() -> None:
    handoff, diagnostic = extract_governed_handoff(
        '{"summary": "done", "checks": [], "artifacts": []}'
    )
    assert diagnostic is None
    assert handoff is not None
    assert handoff["summary"] == "done"


def test_extract_governed_handoff_reports_diagnostic_on_non_conforming_text() -> None:
    handoff, diagnostic = extract_governed_handoff("I finished the task, trust me.")
    assert handoff is None
    assert diagnostic is not None
