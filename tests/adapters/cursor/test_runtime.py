"""WU-P4-RUNTIME — Cursor runtime, RuntimeResult and CG-012 tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from adapters.cursor.runtime.execute import collect_runtime_result, execute_runtime
from adapters.cursor.runtime.results import validate_runtime_result

from governed_ai.adapters.cursor import CursorAdapter
from governed_ai.adapters.spi import ExecutionRequest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_SHA = "a" * 40


def _sample_request(execution_id: str = "EXE-CG012-TEST") -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id=execution_id,
        correlation_id="COR-CG012-TEST",
        adapter={"id": "cursor", "version": "0.5.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": "backend-developer",
            "role_revision": "1.0.0",
            "procedure_id": "implement-work-unit",
            "procedure_revision": "1.0.0",
        },
        project_id="runtime-test",
        work_unit_id="WU-RUNTIME-TEST",
        base_sha=BASE_SHA,
        context_package_ref="CTX-RUNTIME",
        resolved_scope=["src/"],
        approvals=[],
        requested_at="2026-08-29T18:00:00+00:00",
    )


def _write_minimal_project(root: Path) -> None:
    ai = root / ".ai-team"
    (ai / "work-units").mkdir(parents=True)
    (ai / "events").mkdir(parents=True)
    (ai / "state").mkdir(parents=True)
    wu = {
        "id": "WU-RUNTIME-TEST",
        "title": "Runtime test",
        "objective": {"result": "test"},
        "scope": {"include": [], "exclude": []},
        "expected_behavior": "test",
        "acceptance_criteria": [],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {},
        "status": "in_progress",
        "revision": 1,
        "created_at": "2026-08-29T10:00:00+00:00",
        "updated_at": "2026-08-29T10:00:00+00:00",
    }
    (ai / "work-units" / "WU-RUNTIME-TEST.yaml").write_text(
        yaml.safe_dump(wu, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (ai / "state" / "project-state.yaml").write_text(
        "project_id: runtime-test\nphase: execution\n",
        encoding="utf-8",
    )


def _business_state_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for folder in ("work-units", "events", "state", "decisions", "findings"):
        base = root / ".ai-team" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yaml")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_ad009_runtime_result_has_required_identities(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    request = _sample_request()
    result = execute_runtime(tmp_path, request)

    assert result["execution_id"] == "EXE-CG012-TEST"
    assert result["adapter"]["id"] == "cursor"
    assert result["contract"]["role_id"] == "backend-developer"
    assert result["contract"]["procedure_id"] == "implement-work-unit"
    assert result["status"] == "blocked"
    assert result["started_at"]
    assert result["finished_at"]
    assert result["artifacts"]
    assert result["artifacts"][0]["sha256"].startswith("sha256:")
    assert validate_runtime_result(dict(result)) == []


def test_cg012_succeeded_without_commands_leaves_business_state_unchanged(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    before = _business_state_digest(tmp_path)
    request = _sample_request()
    result = execute_runtime(tmp_path, request)
    after = _business_state_digest(tmp_path)

    assert result["status"] == "blocked"
    assert result.get("requested_commands") == []
    assert before == after


def test_collect_reads_persisted_runtime_result(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    request = _sample_request("EXE-COLLECT-001")
    execute_runtime(tmp_path, request)
    collected = collect_runtime_result(tmp_path, "EXE-COLLECT-001")
    assert collected["execution_id"] == "EXE-COLLECT-001"
    assert collected["contract"]["role_id"] == "backend-developer"


def test_cursor_adapter_spi_execute_and_collect(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    adapter = CursorAdapter(
        project_root=tmp_path,
        bundle_dir=REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1",
    )
    request = _sample_request("EXE-SPI-001")
    result = adapter.execute(request)
    again = adapter.collect("EXE-SPI-001")
    assert result == again
    stored = json.loads(
        (tmp_path / ".ai-team/runtime-results/EXE-SPI-001.json").read_text(encoding="utf-8")
    )
    assert stored["contract"]["role_id"] == "backend-developer"


def test_preflight_report_structure_from_runtime_module() -> None:
    from adapters.cursor.runtime.checks import collect_preflight_report

    report = collect_preflight_report(REPO_ROOT)
    assert "platform" in report
    assert "hooks_config" in report
    assert "project_cli" in report


def test_core_diagnostics_separate_from_cursor(tmp_path: Path) -> None:
    from governed_ai.core.diagnostics import collect_in_flight_work_units

    _write_minimal_project(tmp_path)
    in_flight = collect_in_flight_work_units(tmp_path)
    assert in_flight == [("WU-RUNTIME-TEST", "in_progress")]
