"""Claude Code runtime — stub execute/collect and RuntimeResult (CG-012)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from adapters.claude_code.runtime.execute import collect_runtime_result, execute_runtime
from adapters.claude_code.runtime.results import validate_runtime_result

from governed_ai.adapters.claude_code import ClaudeCodeAdapter
from governed_ai.adapters.spi import ExecutionRequest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_SHA = "a" * 40


def _sample_request(execution_id: str = "EXE-CC-RUNTIME-TEST") -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id=execution_id,
        correlation_id="COR-CC-RUNTIME-TEST",
        adapter={"id": "claude-code", "version": "0.1.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": "backend-developer",
            "role_revision": "1.0.0",
            "procedure_id": "implement-work-unit",
            "procedure_revision": "1.0.0",
        },
        project_id="runtime-test",
        work_unit_id="WU-CC-RUNTIME-TEST",
        base_sha=BASE_SHA,
        context_package_ref="CTX-RUNTIME",
        resolved_scope=["src/"],
        approvals=[],
        requested_at="2026-09-15T18:00:00+00:00",
    )


def _write_minimal_project(root: Path) -> None:
    ai = root / ".ai-team"
    (ai / "work-units").mkdir(parents=True)
    (ai / "events").mkdir(parents=True)
    (ai / "state").mkdir(parents=True)
    wu = {
        "id": "WU-CC-RUNTIME-TEST",
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
        "created_at": "2026-09-15T10:00:00+00:00",
        "updated_at": "2026-09-15T10:00:00+00:00",
    }
    (ai / "work-units" / "WU-CC-RUNTIME-TEST.yaml").write_text(
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


def test_execute_runtime_always_stubs_in_this_increment(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    request = _sample_request()
    result = execute_runtime(tmp_path, request)

    assert result["execution_id"] == "EXE-CC-RUNTIME-TEST"
    assert result["adapter"]["id"] == "claude-code"
    assert result["contract"]["role_id"] == "backend-developer"
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
    request = _sample_request("EXE-CC-COLLECT-001")
    execute_runtime(tmp_path, request)
    collected = collect_runtime_result(tmp_path, "EXE-CC-COLLECT-001")
    assert collected["execution_id"] == "EXE-CC-COLLECT-001"
    assert collected["contract"]["role_id"] == "backend-developer"
    runtime_artifact = next(
        item for item in collected["artifacts"] if item["kind"] == "runtime_result"
    )
    stored_path = tmp_path / runtime_artifact["path"]
    assert runtime_artifact["sha256"] == "sha256:" + hashlib.sha256(
        stored_path.read_bytes()
    ).hexdigest()


def test_claude_code_adapter_spi_execute_and_collect(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    adapter = ClaudeCodeAdapter(
        project_root=tmp_path,
        bundle_dir=REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1",
    )
    request = _sample_request("EXE-CC-SPI-001")
    result = adapter.execute(request)
    again = adapter.collect("EXE-CC-SPI-001")
    assert result == again
    stored = json.loads(
        (tmp_path / ".ai-team/runtime-results/EXE-CC-SPI-001.json").read_text(encoding="utf-8")
    )
    assert stored["contract"]["role_id"] == "backend-developer"
    assert stored["adapter"]["id"] == "claude-code"
