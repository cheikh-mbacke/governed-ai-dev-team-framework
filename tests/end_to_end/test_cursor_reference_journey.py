"""Document 14 §10 reference journey — L3 simulated Cursor runtime (deterministic)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from adapters.cursor.runtime.execute import execute_runtime
from governed_ai.adapters.cursor import CursorAdapter
from governed_ai.adapters.spi import ExecutionRequest
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.commands.legacy_cli import RecordGateArgs, translate_record_gate
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"
BASE_SHA = "c" * 40


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def _business_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for folder in ("work-units", "events", "state", "decisions", "evidence", "observations"):
        base = root / ".ai-team" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yaml")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _sample_execution_request(execution_id: str = "EXE-JOURNEY-001") -> ExecutionRequest:
    return ExecutionRequest(
        protocol_version="1.0",
        execution_id=execution_id,
        correlation_id="COR-JOURNEY-001",
        adapter={"id": "cursor", "version": "0.5.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "d" * 64,
            "role_id": "backend-developer",
            "role_revision": "1.0.0",
            "procedure_id": "implement-work-unit",
            "procedure_revision": "1.0.0",
        },
        project_id="journey-test",
        work_unit_id="WU-JOURNEY-001",
        base_sha=BASE_SHA,
        context_package_ref="CTX-JOURNEY",
        resolved_scope=["src/"],
        approvals=[],
        requested_at="2026-08-29T20:00:00+00:00",
    )


def test_l3_fresh_install_preflight_validate_and_record_v2(tmp_path: Path) -> None:
    target = tmp_path / "witness"
    install = _run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "journey-test",
            "--project-name",
            "Journey Test",
        ],
        cwd=REPO_ROOT,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    record_path = target / ".ai-team" / "installation-record.json"
    assert record_path.is_file()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["schema_version"] == 3
    assert record["active_adapter_id"] == "cursor"
    assert record_path.stat().st_mtime >= (target / ".ai-team" / "framework-version.json").stat().st_mtime

    profile = yaml.safe_load((target / ".ai-team" / "project-profile.yaml").read_text(encoding="utf-8"))
    assert profile["active_adapter_id"] == "cursor"

    preflight = _run([sys.executable, "scripts/ai-team/preflight.py"], cwd=target)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr

    diagnose = _run([sys.executable, "scripts/ai-team/diagnose.py"], cwd=target)
    assert diagnose.returncode == 0, diagnose.stdout + diagnose.stderr

    validate = _run([sys.executable, "scripts/ai-team/validate.py"], cwd=target)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "ERROR" not in validate.stdout

    assert not any((target / ".ai-team" / "events").glob("EVT-*.yaml"))
    assert not any((target / ".ai-team" / "work-units").glob("WU-*.yaml"))


def _git_member(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    assert _run(["git", "init", "-q", "-b", "main"], cwd=root).returncode == 0
    assert _run(["git", "config", "user.name", "Journey"], cwd=root).returncode == 0
    assert _run(
        ["git", "config", "user.email", "journey@example.invalid"], cwd=root
    ).returncode == 0
    (root / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert _run(["git", "add", "."], cwd=root).returncode == 0
    assert _run(["git", "commit", "-qm", "fixture"], cwd=root).returncode == 0
    return root


def _register_out_of_tree_member(instance: Path, member: Path) -> None:
    for command in (
        [
            sys.executable,
            "scripts/ai-team/ensemble.py",
            "register-ensemble",
            "--id",
            "journey",
        ],
        [
            sys.executable,
            "scripts/ai-team/ensemble.py",
            "register-member",
            "--ensemble",
            "journey",
            "--id",
            "app",
            "--kind",
            "service",
            "--path",
            str(member),
        ],
        [
            sys.executable,
            "scripts/ai-team/ensemble.py",
            "set-active",
            "--id",
            "journey",
        ],
    ):
        result = _run(command, cwd=instance)
        assert result.returncode == 0, result.stdout + result.stderr


def test_l3_reference_journey_g1_runtime_observation_without_core_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # L3 journey must stay on the harness stub (never spend Cursor agent credits).
    monkeypatch.delenv("GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH", raising=False)

    target = tmp_path / "journey"
    install = _run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "journey-test",
            "--project-name",
            "Journey Test",
        ],
        cwd=REPO_ROOT,
    )
    assert install.returncode == 0, install.stderr

    member = _git_member(tmp_path / "journey-app")
    _register_out_of_tree_member(target, member)

    wu_dir = target / ".ai-team" / "work-units"
    wu_dir.mkdir(parents=True, exist_ok=True)
    (wu_dir / "WU-JOURNEY-001.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-JOURNEY-001",
                "title": "Journey WU",
                "objective": {"result": "L3 journey"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "Gateway and runtime boundaries hold",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "ready",
                "revision": 1,
                "created_at": "2026-08-29T20:00:00+00:00",
                "updated_at": "2026-08-29T20:00:00+00:00",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    state_path = target / ".ai-team" / "state" / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["work_units"] = {"WU-JOURNEY-001": {"status": "ready", "milestone": "M-P6", "risk": "low"}}
    state_path.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8")

    before = _business_digest(target)

    envelope = translate_record_gate(
        RecordGateArgs(
            gate="G1",
            status="approved",
            by="journey-operator",
            note="Plan approved for L3 journey",
            authorization_id="HAUTH-journey-g1",
        )
    )
    workspace = Workspace.from_root(target)
    gateway = CommandGateway(workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0, receipt
    assert (target / ".ai-team" / "decisions").glob("*.yaml")

    adapter = CursorAdapter(
        project_root=target,
        bundle_dir=REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1",
    )
    runtime_result = adapter.execute(_sample_execution_request())
    assert runtime_result["status"] == "blocked"
    assert (target / ".ai-team/runtime-results/EXE-JOURNEY-001.json").is_file()

    execute_runtime(target, _sample_execution_request("EXE-JOURNEY-002"))

    feedback = _run(
        [
            sys.executable,
            "scripts/ai-team/feedback.py",
            "record",
            "--category",
            "tooling",
            "--symptom",
            "L3 journey observation",
        ],
        cwd=target,
    )
    assert feedback.returncode == 0, feedback.stderr + feedback.stdout

    after = _business_digest(target)
    assert before != after
    assert any((target / ".ai-team" / "decisions").glob("*.yaml"))
    assert any((target / ".ai-team" / "observations").glob("OBS-*.yaml"))
    wu_text = (target / ".ai-team" / "work-units" / "WU-JOURNEY-001.yaml").read_text(encoding="utf-8")
    assert "status: done" not in wu_text


def test_l3_update_dry_run_on_installed_witness(tmp_path: Path) -> None:
    target = tmp_path / "update-journey"
    assert (
        _run(
            [
                sys.executable,
                str(INSTALL),
                "--target",
                str(target),
                "--project-id",
                "journey-update",
                "--project-name",
                "Journey Update",
            ],
            cwd=REPO_ROOT,
        ).returncode
        == 0
    )

    marker = target / ".ai-team" / "project-profile.yaml"
    original = marker.read_bytes()
    dry = _run(
        [sys.executable, str(INSTALL), "--target", str(target), "--update", "--dry-run"],
        cwd=REPO_ROOT,
    )
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert marker.read_bytes() == original


def test_l4_real_cursor_reported_not_run() -> None:
    from tests.end_to_end.conformity_report import ConformityReport, l4_availability_note

    report = ConformityReport()
    report.levels["L4"] = "not_run"
    report.deviations.append(l4_availability_note())
    assert report.levels["L4"] == "not_run"
    assert l4_availability_note() in report.deviations
