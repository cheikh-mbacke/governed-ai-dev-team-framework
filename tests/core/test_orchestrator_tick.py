"""Orchestrator Étape 1 — run_scheduling_tick (Document 6, orchestrator prerequisite).

One tick, one decision: start a ready Work Unit, reassign a stale lease,
dispatch an execution attempt via a fake AdapterSPI, or stay idle. Real
wall-clock looping lives only in scripts/ai-team/orchestrate.py and is
deliberately not unit tested here — see
docs/framework-design/requirements/mode-nuit-preuve-resilience-couverture.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from tests.core.workspace_helpers import (
    FABRIC_ROOT,
    PAYLOAD_AI_TEAM,
    write_installed_client_profile,
)

from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.orchestrator.git_workspace import head_sha
from governed_ai.core.orchestrator.tick import run_scheduling_tick
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRANT_ID = "GRANT-DEFAULT"


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root}", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def _seed_grant(workspace: Workspace, grant_id: str, *, work_unit_ids: list[str]) -> None:
    grants_dir = workspace.ai_team / "run-authorization-grants"
    grants_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "id": grant_id,
        "revision": 1,
        "issued_at": "2026-08-30T00:00:00+00:00",
        "issuing_authority": "cheikh MBACKE",
        "work_unit_ids": work_unit_ids,
        "allowed_commands": [],
        "allowed_environments": ["development", "test"],
        "maximum_spend": None,
        "maximum_duration_hours": 12,
        "expires_at": "2099-01-01T00:00:00+00:00",
        "maximum_uses": 1000,
        "uses_count": 0,
        "excluded_actions": [
            "RecordGateDecision",
            "RecordAcceptance",
            "ResolveDecisionRequest",
            "ModifyConstitution",
            "ProductionAction",
        ],
        "revoked_at": None,
        "revoked_reason": None,
    }
    (grants_dir / f"{grant_id}.json").write_text(json.dumps(document, indent=2), encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team)
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    (ai_team / "work-units").mkdir(parents=True)
    ws = Workspace.from_root(tmp_path)
    _seed_grant(ws, DEFAULT_GRANT_ID, work_unit_ids=["WU-A", "WU-B"])
    return ws


def _seed_context_package(
    workspace: Workspace,
    work_unit_id: str,
    *,
    context_id: str | None = None,
) -> str:
    ctx_id = context_id or f"CTX-{work_unit_id}"
    packages = workspace.ai_team / "context-packages"
    packages.mkdir(parents=True, exist_ok=True)
    document = {
        "id": ctx_id,
        "work_unit": work_unit_id,
        "role": "backend-developer",
        "required_contracts": [],
        "completeness_status": "complete",
        "missing_inputs": [],
        "items": [
            {
                "level": "L3_work_unit",
                "source": f".ai-team/work-units/{work_unit_id}.yaml",
                "provenance": "authoritative",
                "reason": "seeded for tick tests",
            }
        ],
        "open_context_requests": [],
    }
    (packages / f"{ctx_id}.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    return ctx_id


def _seed_work_unit(
    workspace: Workspace,
    work_unit_id: str,
    *,
    status: str,
    scope_include: list[str] | None = None,
    context_package_ref: str | None | bool = True,
) -> None:
    ctx_ref: str | None
    if context_package_ref is True:
        ctx_ref = _seed_context_package(workspace, work_unit_id)
    elif context_package_ref is False or context_package_ref is None:
        ctx_ref = None
    else:
        ctx_ref = str(context_package_ref)
        _seed_context_package(workspace, work_unit_id, context_id=ctx_ref)
    document = {
        "id": work_unit_id,
        "title": "Test work unit",
        "objective": {"result": "test"},
        "scope": {"include": scope_include or [], "exclude": []},
        "expected_behavior": "test behavior",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {"unit_tests": True},
        "status": status,
        "revision": 1,
        "created_at": "2026-08-30T00:00:00+00:00",
        "updated_at": "2026-08-30T00:00:00+00:00",
        "events": [],
        "evidence": [],
        "context_package_ref": ctx_ref,
        "outcomes": {
            "review_status": "pending",
            "audit_status": "not_required",
            "critical_open_items": [],
            "defects": [],
            "audit_findings": [],
            "human_acceptance": None,
        },
    }
    path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def _actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-tick-test",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _envelope(command_type: str, *, target: dict, payload: dict, key: str, **extra: dict) -> dict:
    envelope = {
        "protocol_version": "1.0",
        "command_id": f"CMD-{key}",
        "idempotency_key": f"idem-{key}",
        "correlation_id": "COR-tick-test",
        "type": command_type,
        "issued_at": "2026-08-30T02:00:00Z",
        "actor": _actor(),
        "target": target,
        "payload": payload,
    }
    envelope.update(extra)
    return envelope


def _open_run(
    run_id: str,
    *,
    work_unit_ids: list[str],
    grant_id: str = DEFAULT_GRANT_ID,
    maximum_parallel_workers: int | None = None,
) -> dict:
    payload = {
        "id": run_id,
        "opened_by": "operator",
        "work_unit_ids": work_unit_ids,
        "status": "active",
        "preflight": {"python": {"status": "pass", "detail": "ok"}},
    }
    if maximum_parallel_workers is not None:
        payload["maximum_parallel_workers"] = maximum_parallel_workers
    return _envelope(
        "OpenRun",
        target={"kind": "run", "id": run_id},
        payload=payload,
        key=f"open-{run_id}",
        run_authorization={"grant_id": grant_id},
    )


def _expire_lease_heartbeat(workspace: Workspace, lease_id: str) -> None:
    lease_path = workspace.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    document = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
    stale = datetime.now(UTC) - timedelta(minutes=document["stalled_after_minutes"] + 1)
    document["heartbeat_at"] = stale.isoformat()
    lease_path.write_text(yaml.safe_dump(document), encoding="utf-8")


class FakeAdapter:
    """Minimal AdapterSPI double: only `execute()` matters to the tick."""

    def __init__(self, results: list[dict]) -> None:
        self._results = list(results)
        self.requests: list[dict] = []

    def describe(self):  # pragma: no cover - not exercised by the tick
        raise NotImplementedError

    def check_compatibility(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def compile(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def execute(self, request: dict) -> dict:
        self.requests.append(request)
        return self._results.pop(0)

    def collect(self, execution_id: str):  # pragma: no cover
        raise NotImplementedError


def _succeeded_result(
    summary: str = "ok", *, check_name: str = "implementation", changed_sha: bool = True
) -> dict:
    return {
        "status": "succeeded",
        "summary": summary,
        "checks": [
            {"name": check_name, "status": "passed", "evidence_ref": f"EV-{check_name}"}
        ],
        "artifacts": [
            {"kind": "test", "path": "evidence.json", "sha256": "sha256:" + "a" * 64}
        ],
        "workspace": {"result_sha": "b" * 40 if changed_sha else "a" * 40},
        "requested_commands": [],
        "usage": {},
    }


def _succeeded_result_with_checks(
    check_names: list[str], *, changed_sha: bool = True, include_artifact: bool = True
) -> dict:
    return {
        "status": "succeeded",
        "summary": "ok",
        "checks": [
            {"name": name, "status": "passed", "evidence_ref": f"EV-{name}"}
            for name in check_names
        ],
        "artifacts": (
            [{"kind": "test", "path": "evidence.json", "sha256": "sha256:" + "a" * 64}]
            if include_artifact
            else []
        ),
        "workspace": {"result_sha": "b" * 40 if changed_sha else "a" * 40},
        "requested_commands": [],
        "usage": {},
    }


def test_tick_starts_a_ready_work_unit(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-001", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="ready")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-001", adapter=FakeAdapter([]), worker_id="w1"
    )

    assert result.action == "started_work_unit"
    assert result.work_unit_id == "WU-A"
    wu_document = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu_document["status"] == "in_progress"
    lease_id = result.details["lease_id"]
    lease_document = yaml.safe_load(
        (workspace.ai_team / "runs" / "leases" / f"{lease_id}.yaml").read_text(encoding="utf-8")
    )
    assert lease_document["epoch"] == 1


def test_tick_executes_bounded_remediation_then_returns_to_verification(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-REMEDIATE", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="remediation_required")
    adapter = FakeAdapter([_succeeded_result(check_name="implementation")])

    acquired = run_scheduling_tick(
        gateway, workspace, run_id="RUN-REMEDIATE", adapter=adapter, worker_id="w1"
    )
    assert acquired.action == "reacquired_work_unit"

    remediated = run_scheduling_tick(
        gateway, workspace, run_id="RUN-REMEDIATE", adapter=adapter, worker_id="w1"
    )
    assert remediated.action == "advanced_work_unit"
    assert remediated.details["from"] == "remediation_required"
    assert remediated.details["to"] == "verification"
    attempt = yaml.safe_load(
        next((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")).read_text(
            encoding="utf-8"
        )
    )
    assert attempt["step"] == "remediation"


def test_implementation_evidence_gate_accepts_explicit_ac_checks_without_implementation_name(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-AC-OK", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    wu_path = workspace.ai_team / "work-units" / "WU-A.yaml"
    wu = yaml.safe_load(wu_path.read_text(encoding="utf-8"))
    wu["acceptance_criteria"] = [
        {"AC-1": "parent module wired"},
        {"AC-2": "health endpoint public"},
        {"AC-3": "flyway migration"},
        {"AC-4": "compose healthy"},
        {"AC-5": "no foreign migrations"},
    ]
    wu_path.write_text(yaml.safe_dump(wu), encoding="utf-8")
    adapter = FakeAdapter(
        [
            _succeeded_result_with_checks(
                ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"], changed_sha=True
            )
        ]
    )

    acquired = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-OK", adapter=adapter, worker_id="w1"
    )
    assert acquired.action == "reacquired_work_unit"
    advanced = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-OK", adapter=adapter, worker_id="w1"
    )
    assert advanced.action == "advanced_work_unit"
    assert advanced.details["from"] == "in_progress"
    assert advanced.details["to"] == "verification"


def test_implementation_evidence_gate_rejects_partial_ac_when_wu_declares_ids(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-AC-PARTIAL", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    wu_path = workspace.ai_team / "work-units" / "WU-A.yaml"
    wu = yaml.safe_load(wu_path.read_text(encoding="utf-8"))
    wu["acceptance_criteria"] = [
        {"AC-1": "one"},
        {"AC-2": "two"},
        {"AC-3": "three"},
    ]
    wu_path.write_text(yaml.safe_dump(wu), encoding="utf-8")
    adapter = FakeAdapter(
        [_succeeded_result_with_checks(["AC-1", "AC-2"], changed_sha=True)]
    )

    acquired = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-PARTIAL", adapter=adapter, worker_id="w1"
    )
    assert acquired.action == "reacquired_work_unit"
    failed = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-PARTIAL", adapter=adapter, worker_id="w1"
    )
    assert failed.action == "recorded_attempt"
    assert failed.details["status"] == "failed"
    attempt = yaml.safe_load(
        next((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")).read_text(
            encoding="utf-8"
        )
    )
    assert attempt["status"] == "failed"
    assert "AC-3" in attempt["summary"]


def test_implementation_evidence_gate_rejects_check_without_evidence_ref(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-AC-NOEV", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    result = _succeeded_result_with_checks(["AC-1"], changed_sha=True)
    result["checks"] = [{"name": "AC-1", "status": "passed"}]
    adapter = FakeAdapter([result])

    acquired = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-NOEV", adapter=adapter, worker_id="w1"
    )
    assert acquired.action == "reacquired_work_unit"
    failed = run_scheduling_tick(
        gateway, workspace, run_id="RUN-AC-NOEV", adapter=adapter, worker_id="w1"
    )
    assert failed.action == "recorded_attempt"
    assert failed.details["status"] == "failed"


def test_review_evidence_gate_still_requires_named_check() -> None:
    from governed_ai.core.orchestrator.tick import _evidence_error

    result = _succeeded_result_with_checks(["AC-1", "AC-2"], changed_sha=False)
    error = _evidence_error(
        result,
        required_checks=("code_review",),
        require_changed_sha=False,
        base_sha="a" * 40,
        work_unit={"acceptance_criteria": [{"AC-1": "x"}, {"AC-2": "y"}]},
    )
    assert error is not None
    assert "code_review" in error


def test_unattended_run_stops_when_adapter_cannot_isolate_workers(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-NO-ISOLATION", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    run_path = workspace.ai_team / "runs" / "RUN-NO-ISOLATION.yaml"
    run = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    run["autonomy_preset"] = "unattended_conservative"
    run_path.write_text(yaml.safe_dump(run), encoding="utf-8")

    first = run_scheduling_tick(
        gateway, workspace, run_id="RUN-NO-ISOLATION", adapter=FakeAdapter([]), worker_id="w1"
    )
    assert first.action == "reacquired_work_unit"
    stopped = run_scheduling_tick(
        gateway, workspace, run_id="RUN-NO-ISOLATION", adapter=FakeAdapter([]), worker_id="w1"
    )
    assert stopped.action == "run_stopped"
    assert stopped.details["stop_condition"] == "worker_isolation_unguaranteed"
    assert "feedback_submit" in stopped.details
    assert stopped.details["feedback_submit"]["transmission_status"] == "failed"
    submit_path = workspace.root / stopped.details["feedback_submit"]["path"]
    assert submit_path.is_file()
    assert "outbox" in submit_path.as_posix()


def test_tick_reassigns_a_stale_lease(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-002", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-TICK-1"},
            payload={
                "id": "LEASE-TICK-1",
                "run_id": "RUN-TICK-002",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-1",
        )
    )
    _expire_lease_heartbeat(workspace, "LEASE-TICK-1")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-002", adapter=FakeAdapter([]), worker_id="w2"
    )

    assert result.action == "reassigned_lease"
    assert result.work_unit_id == "WU-A"
    old_lease = yaml.safe_load(
        (workspace.ai_team / "runs" / "leases" / "LEASE-TICK-1.yaml").read_text(encoding="utf-8")
    )
    assert old_lease["status"] == "superseded"
    new_lease = yaml.safe_load(
        (workspace.ai_team / "runs" / "leases" / f"{result.details['lease_id']}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert new_lease["epoch"] == 2


def test_tick_dispatches_execution_and_advances_on_success(workspace: Workspace) -> None:
    """Document 6 §9.3/orchestrator.json — a successful step always advances the Work Unit."""
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-003", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-TICK-2"},
            payload={
                "id": "LEASE-TICK-2",
                "run_id": "RUN-TICK-003",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-2",
        )
    )
    lease_path = workspace.ai_team / "runs" / "leases" / "LEASE-TICK-2.yaml"
    heartbeat_before = yaml.safe_load(lease_path.read_text(encoding="utf-8"))["heartbeat_at"]

    adapter = FakeAdapter([_succeeded_result("implemented the thing")])
    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-003", adapter=adapter, worker_id="w1"
    )

    assert result.action == "advanced_work_unit"
    assert result.details["from"] == "in_progress"
    assert result.details["to"] == "verification"
    assert len(adapter.requests) == 1
    assert adapter.requests[0]["work_unit_id"] == "WU-A"

    attempt = yaml.safe_load(
        (
            workspace.ai_team / "runs" / "execution-attempts" / f"{result.details['attempt_id']}.yaml"
        ).read_text(encoding="utf-8")
    )
    assert attempt["status"] == "succeeded"
    assert attempt["step"] == "sandbox_implementation"
    assert attempt["summary"] == "implemented the thing"

    wu_document = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu_document["status"] == "verification"

    heartbeat_after = yaml.safe_load(lease_path.read_text(encoding="utf-8"))["heartbeat_at"]
    assert heartbeat_after != heartbeat_before


def test_out_of_scope_write_stops_the_whole_run(workspace: Workspace) -> None:
    """Document 6 §9.5 — a write outside a Work Unit's declared scope is one of
    the fixed conditions that stops the whole Run, not just this Work Unit.
    Before this fix, `_implementation_boundary_error` detected the violation
    but only failed the single attempt, leaving the Run active."""
    root = workspace.root
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "l4@example.test")
    _git(root, "config", "user.name", "L4 Test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "test: base")

    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-BOUNDARY-001", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress", scope_include=["src/**"])
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-BOUNDARY-1"},
            payload={
                "id": "LEASE-BOUNDARY-1",
                "run_id": "RUN-BOUNDARY-001",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-boundary-1",
        )
    )

    class OutOfScopeAdapter:
        def describe(self):
            return {"capabilities": {"isolated_worktree": True}}

        def check_compatibility(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def compile(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def collect(self, execution_id: str):  # pragma: no cover
            raise NotImplementedError

        def execute(self, request: dict) -> dict:
            worker_root = Path(request["execution_workspace"])
            outside = worker_root / "unrelated" / "escape.txt"
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("outside scope\n", encoding="utf-8")
            _git(worker_root, "add", "unrelated/escape.txt")
            _git(worker_root, "commit", "-m", "feat(WU-A): out-of-scope write")
            result = _succeeded_result()
            result["workspace"] = {"result_sha": head_sha(worker_root)}
            return result

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-BOUNDARY-001",
        adapter=OutOfScopeAdapter(),
        worker_id="w1",
    )

    assert result.action == "run_stopped"
    assert result.details["stop_condition"] == "out_of_workspace_write"
    run_document = yaml.safe_load(
        (workspace.ai_team / "runs" / "RUN-BOUNDARY-001.yaml").read_text(encoding="utf-8")
    )
    assert run_document["status"] == "stopped"
    assert run_document["stop_condition"] == "out_of_workspace_write"

    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    attempt = yaml.safe_load(next(attempts_dir.glob("*.yaml")).read_text(encoding="utf-8"))
    assert attempt["status"] == "failed"
    assert "out-of-scope writes detected" in attempt["summary"]

    lease = yaml.safe_load(
        (workspace.ai_team / "runs" / "leases" / "LEASE-BOUNDARY-1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert lease["status"] == "revoked"


def test_wu_evidence_write_does_not_stop_run_when_product_stays_in_scope(
    workspace: Workspace,
) -> None:
    root = workspace.root
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "l4@example.test")
    _git(root, "config", "user.name", "L4 Test")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    _git(root, "add", "src/app.py")
    _git(root, "commit", "-m", "test: base")

    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-BOUNDARY-EVIDENCE", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress", scope_include=["src/**"])
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-BOUNDARY-EV"},
            payload={
                "id": "LEASE-BOUNDARY-EV",
                "run_id": "RUN-BOUNDARY-EVIDENCE",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-boundary-ev",
        )
    )

    class EvidenceAndProductAdapter:
        def describe(self):
            return {"capabilities": {"isolated_worktree": True}}

        def check_compatibility(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def compile(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def collect(self, execution_id: str):  # pragma: no cover
            raise NotImplementedError

        def execute(self, request: dict) -> dict:
            worker_root = Path(request["execution_workspace"])
            product = worker_root / "src" / "app.py"
            product.write_text("print('updated')\n", encoding="utf-8")
            evidence = worker_root / ".ai-team" / "evidence" / "WU-A" / "ac-1.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("passed\n", encoding="utf-8")
            _git(worker_root, "add", "src/app.py", ".ai-team/evidence/WU-A/ac-1.md")
            _git(worker_root, "commit", "-m", "feat(WU-A): product + evidence")
            result = _succeeded_result()
            result["workspace"] = {"result_sha": head_sha(worker_root)}
            return result

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-BOUNDARY-EVIDENCE",
        adapter=EvidenceAndProductAdapter(),
        worker_id="w1",
    )
    assert result.action == "advanced_work_unit"
    assert result.details["to"] == "verification"


def test_work_unit_yaml_write_stops_the_whole_run(workspace: Workspace) -> None:
    root = workspace.root
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "l4@example.test")
    _git(root, "config", "user.name", "L4 Test")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    _git(root, "add", "src/app.py")
    _git(root, "commit", "-m", "test: base")

    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-BOUNDARY-WU", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress", scope_include=["src/**"])
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-BOUNDARY-WU"},
            payload={
                "id": "LEASE-BOUNDARY-WU",
                "run_id": "RUN-BOUNDARY-WU",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-boundary-wu",
        )
    )

    class MutateWorkUnitAdapter:
        def describe(self):
            return {"capabilities": {"isolated_worktree": True}}

        def check_compatibility(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def compile(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

        def collect(self, execution_id: str):  # pragma: no cover
            raise NotImplementedError

        def execute(self, request: dict) -> dict:
            worker_root = Path(request["execution_workspace"])
            wu_path = worker_root / ".ai-team" / "work-units" / "WU-A.yaml"
            wu_path.parent.mkdir(parents=True, exist_ok=True)
            wu_path.write_text("id: WU-A\nstatus: done\n", encoding="utf-8")
            _git(worker_root, "add", ".ai-team/work-units/WU-A.yaml")
            _git(worker_root, "commit", "-m", "feat(WU-A): mutate work unit")
            result = _succeeded_result()
            result["workspace"] = {"result_sha": head_sha(worker_root)}
            return result

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-BOUNDARY-WU",
        adapter=MutateWorkUnitAdapter(),
        worker_id="w1",
    )
    assert result.action == "run_stopped"
    assert result.details["stop_condition"] == "out_of_workspace_write"
    attempt = yaml.safe_load(
        next(
            (workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")
        ).read_text(encoding="utf-8")
    )
    assert "forbidden governance writes" in attempt["summary"]


def test_tick_walks_a_work_unit_through_verification_review_audit_to_human_test(
    workspace: Workspace,
) -> None:
    """The loop stops at human_test — done requires human acceptance, never auto-decided."""
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-006", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-TICK-6"},
            payload={
                "id": "LEASE-TICK-6",
                "run_id": "RUN-TICK-006",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-6",
        )
    )

    expected_transitions = [
        ("in_progress", "verification", "implementation"),
        ("verification", "review", "tests"),
        ("review", "audit", "code_review"),
    ]
    for from_status, to_status, check_name in expected_transitions:
        result = run_scheduling_tick(
            gateway,
            workspace,
            run_id="RUN-TICK-006",
            adapter=FakeAdapter(
                [_succeeded_result(check_name=check_name, changed_sha=from_status == "in_progress")]
            ),
            worker_id="w1",
        )
        assert result.action == "advanced_work_unit"
        assert result.details["from"] == from_status
        assert result.details["to"] == to_status

    security = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-TICK-006",
        adapter=FakeAdapter(
            [_succeeded_result(check_name="security_review", changed_sha=False)]
        ),
        worker_id="w1",
    )
    assert security.action == "completed_security_review"

    audit = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-TICK-006",
        adapter=FakeAdapter([_succeeded_result(check_name="audit", changed_sha=False)]),
        worker_id="w1",
    )
    assert audit.action == "advanced_work_unit"
    assert audit.details["from"] == "audit"
    assert audit.details["to"] == "human_test"
    assert audit.details["retrospective_id"].startswith("RET-")
    assert len(list((workspace.ai_team / "retrospectives").glob("*.yaml"))) == 1

    wu_document = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu_document["status"] == "human_test"

    # human_test does not map to a dispatchable step: signal human wait instead
    # of silent idle.
    waiting = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-006", adapter=FakeAdapter([]), worker_id="w1"
    )
    assert waiting.action == "awaiting_human"
    assert "WU-A" in waiting.details["waiting_work_unit_ids"]


def test_unattended_run_completion_generates_project_retrospective(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-RETRO", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="human_test")
    run_path = workspace.ai_team / "runs" / "RUN-RETRO.yaml"
    run = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    run["autonomy_preset"] = "unattended_conservative"
    run_path.write_text(yaml.safe_dump(run), encoding="utf-8")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-RETRO", adapter=FakeAdapter([]), worker_id="w1"
    )

    assert result.action == "run_completed"
    assert result.details["retrospective_id"].startswith("RET-")
    retrospective_path = next((workspace.ai_team / "retrospectives").glob("*.yaml"))
    retrospective = yaml.safe_load(retrospective_path.read_text(encoding="utf-8"))
    assert retrospective["scope"]["type"] == "project"


def test_tick_demotes_work_unit_on_convergence_exhaustion(workspace: Workspace) -> None:
    """A non-success that exhausts the convergence loop closes the gap Document 6 §9.3
    left open before this pass: it now has a real consequence on the Work Unit, not
    just a diagnostic event nobody acts on."""
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-004", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-TICK-3"},
            payload={
                "id": "LEASE-TICK-3",
                "run_id": "RUN-TICK-004",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="acquire-3",
        )
    )

    timed_out = {"status": "timed_out", "summary": "same timeout every time"}
    adapter = FakeAdapter([timed_out, timed_out])

    first = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-004", adapter=adapter, worker_id="w1"
    )
    assert first.action == "recorded_attempt"
    assert first.details["status"] == "timed_out"

    second = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-004", adapter=adapter, worker_id="w1"
    )
    assert second.action == "demoted_work_unit"
    assert second.details["from"] == "in_progress"
    assert second.details["to"] == "blocked"
    assert second.details["reason"] == "identical_failure_repeated"

    wu_document = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu_document["status"] == "blocked"

    # blocked does not map to a dispatchable step — Lot 4 stops the Run when
    # every Work Unit is stuck (no_dispatchable_work), rather than idling forever.
    third = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-004", adapter=FakeAdapter([]), worker_id="w1"
    )
    assert third.action == "run_stopped"
    assert third.details["stop_condition"] == "no_dispatchable_work"


def test_tick_is_idle_when_nothing_is_eligible(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-005", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="done")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-TICK-005", adapter=FakeAdapter([]), worker_id="w1"
    )

    assert result.action == "idle"
    assert result.work_unit_id is None


def test_tick_does_not_dispatch_on_another_workers_lease(workspace: Workspace) -> None:
    """Document 6 §11 — with several workers ticking, one never picks up work it does
    not hold the lease for, even if that work unit is otherwise dispatchable."""
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-TICK-007", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-TICK-7"},
            payload={
                "id": "LEASE-TICK-7",
                "run_id": "RUN-TICK-007",
                "work_unit_id": "WU-A",
                "worker_id": "worker-owner",
            },
            key="acquire-7",
        )
    )

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-TICK-007",
        adapter=FakeAdapter([]),
        worker_id="worker-other",
    )

    assert result.action == "idle"


def test_concurrent_ticks_respect_the_parallel_worker_cap(workspace: Workspace) -> None:
    """Real threads, real file contention — Document 6 §11's cap must hold under an
    actual race, not just a simulated one (see mode-nuit-preuve-resilience-couverture.md
    on why most of this codebase's races are simulated rather than real)."""
    import threading

    _seed_grant(workspace, "GRANT-CONCURRENT", work_unit_ids=["WU-A", "WU-B", "WU-C"])
    gateway = CommandGateway(workspace)
    gateway.execute_command(
        _open_run(
            "RUN-TICK-008",
            work_unit_ids=["WU-A", "WU-B", "WU-C"],
            grant_id="GRANT-CONCURRENT",
            maximum_parallel_workers=2,
        )
    )
    for work_unit_id in ("WU-A", "WU-B", "WU-C"):
        _seed_work_unit(workspace, work_unit_id, status="ready")

    class AlwaysSucceeds:
        def execute(self, request):
            role = request["contract"]["role_id"]
            check = {
                "backend-developer": "implementation",
                "qa-test": "tests",
                "code-reviewer": "code_review",
                "security-reviewer": "security_review",
                "auditor": "audit",
            }[role]
            return _succeeded_result(check_name=check, changed_sha=role == "backend-developer")

        def describe(self):  # pragma: no cover
            raise NotImplementedError

        def check_compatibility(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        def compile(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        def collect(self, execution_id):  # pragma: no cover
            raise NotImplementedError

    adapter = AlwaysSucceeds()
    errors: list[Exception] = []

    def _hammer(worker_id: str) -> None:
        try:
            for _ in range(30):
                run_scheduling_tick(
                    gateway, workspace, run_id="RUN-TICK-008", adapter=adapter, worker_id=worker_id
                )
        except Exception as exc:  # pragma: no cover - surfaced via `errors`
            errors.append(exc)

    threads = [threading.Thread(target=_hammer, args=(f"worker-{i}",)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors

    run_document = yaml.safe_load(
        (workspace.ai_team / "runs" / "RUN-TICK-008.yaml").read_text(encoding="utf-8")
    )
    assert len(run_document["leases_by_work_unit"]) <= 2

    statuses = {
        wu_id: yaml.safe_load(
            (workspace.ai_team / "work-units" / f"{wu_id}.yaml").read_text(encoding="utf-8")
        )["status"]
        for wu_id in ("WU-A", "WU-B", "WU-C")
    }
    # During this bounded hammer, exactly two workers may be staffed at once;
    # the third remains ready until one of those workflows reaches release.
    assert list(statuses.values()).count("ready") == 1


def test_tick_raises_for_unknown_run(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    with pytest.raises(FileNotFoundError):
        run_scheduling_tick(
            gateway,
            workspace,
            run_id="RUN-DOES-NOT-EXIST",
            adapter=FakeAdapter([]),
            worker_id="w1",
        )


def test_attempt_is_persisted_started_before_adapter_side_effects(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-STARTED", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-STARTED"},
            payload={
                "id": "LEASE-L4-STARTED",
                "run_id": "RUN-L4-STARTED",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-started-lease",
        )
    )

    class InspectingAdapter(FakeAdapter):
        def execute(self, request: dict) -> dict:
            attempts = list((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml"))
            assert len(attempts) == 1
            assert yaml.safe_load(attempts[0].read_text(encoding="utf-8"))["status"] == "started"
            return super().execute(request)

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-STARTED",
        adapter=InspectingAdapter([_succeeded_result()]),
        worker_id="w1",
    )
    assert result.action == "advanced_work_unit"


def test_revoked_grant_stops_run_before_adapter_launch(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-KILL", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    grant_path = workspace.ai_team / "run-authorization-grants" / f"{DEFAULT_GRANT_ID}.json"
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    grant["revoked_at"] = datetime.now(UTC).isoformat()
    grant["revoked_reason"] = "operator kill switch"
    grant_path.write_text(json.dumps(grant), encoding="utf-8")

    class MustNotRun(FakeAdapter):
        def execute(self, request: dict) -> dict:  # pragma: no cover - safety assertion
            raise AssertionError("adapter launched after grant revocation")

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-KILL",
        adapter=MustNotRun([]),
        worker_id="w1",
    )
    assert result.action == "run_stopped"
    assert result.details["stop_condition"] == "kill_switch"
    run = yaml.safe_load(
        (workspace.ai_team / "runs" / "RUN-L4-KILL.yaml").read_text(encoding="utf-8")
    )
    assert run["status"] == "stopped"


def test_restart_resumes_from_persisted_checkpoint(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-RESTART", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-RESTART"},
            payload={
                "id": "LEASE-L4-RESTART",
                "run_id": "RUN-L4-RESTART",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-restart-lease",
        )
    )
    first = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-RESTART",
        adapter=FakeAdapter([{"status": "failed", "summary": "transient crash"}]),
        worker_id="w1",
    )
    assert first.action == "recorded_attempt"
    assert (workspace.ai_team / "runs" / "checkpoints" / "WU-A.yaml").is_file()

    restarted_gateway = CommandGateway(Workspace.from_root(workspace.root))
    resumed = run_scheduling_tick(
        restarted_gateway,
        Workspace.from_root(workspace.root),
        run_id="RUN-L4-RESTART",
        adapter=FakeAdapter([_succeeded_result("resumed")]),
        worker_id="w1",
    )
    assert resumed.action == "advanced_work_unit"
    assert resumed.details["to"] == "verification"


def test_failed_execution_attempt_auto_records_observation(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-AUTO-OBS", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-AUTO-OBS"},
            payload={
                "id": "LEASE-AUTO-OBS",
                "run_id": "RUN-AUTO-OBS",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="auto-obs-lease",
        )
    )

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-AUTO-OBS",
        adapter=FakeAdapter([{"status": "failed", "summary": "boom"}]),
        worker_id="w1",
    )

    assert result.action == "recorded_attempt"
    observations = list((workspace.ai_team / "observations").glob("*.yaml"))
    assert len(observations) == 1
    observation = yaml.safe_load(observations[0].read_text(encoding="utf-8"))
    assert observation["symptom"] == "boom"
    assert observation["work_unit"] == "WU-A"
    assert observation["category"] == "tooling"
    assert observation["classification"]["origin"] == "framework"
    assert observation["classification"]["confidence"] == "low"
    assert observation["candidate_improvement"]
    assert observation["recorded_by"] == "orchestrator:auto"
    assert observation["occurrence_count"] == 1
    assert observation["recurrence_key"] == "auto:sandbox_implementation:failed"


def test_repeated_failed_attempts_coalesce_auto_observation(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-AUTO-COAL", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-AUTO-COAL"},
            payload={
                "id": "LEASE-AUTO-COAL",
                "run_id": "RUN-AUTO-COAL",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="auto-coal-lease",
        )
    )

    first = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-AUTO-COAL",
        adapter=FakeAdapter([{"status": "failed", "summary": "boom-1"}]),
        worker_id="w1",
    )
    assert first.action == "recorded_attempt"

    second = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-AUTO-COAL",
        adapter=FakeAdapter([{"status": "failed", "summary": "boom-2"}]),
        worker_id="w1",
    )
    assert second.action == "recorded_attempt"

    observations = list((workspace.ai_team / "observations").glob("*.yaml"))
    assert len(observations) == 1
    observation = yaml.safe_load(observations[0].read_text(encoding="utf-8"))
    assert observation["occurrence_count"] == 2
    assert observation["symptom"] == "boom-1"
    assert observation["recurrence_key"] == "auto:sandbox_implementation:failed"
    assert len(observation["evidence_refs"]) == 4


def test_flaky_failure_can_recover_on_bounded_retry(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-FLAKY", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-FLAKY"},
            payload={
                "id": "LEASE-L4-FLAKY",
                "run_id": "RUN-L4-FLAKY",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-flaky-lease",
        )
    )
    adapter = FakeAdapter(
        [
            {"status": "failed", "summary": "flaky network fixture"},
            _succeeded_result("retry passed"),
        ]
    )
    assert run_scheduling_tick(
        gateway, workspace, run_id="RUN-L4-FLAKY", adapter=adapter, worker_id="w1"
    ).action == "recorded_attempt"
    recovered = run_scheduling_tick(
        gateway, workspace, run_id="RUN-L4-FLAKY", adapter=adapter, worker_id="w1"
    )
    assert recovered.action == "advanced_work_unit"


def test_adapter_permission_failure_pauses_work_unit(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-PERM", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-PERM"},
            payload={
                "id": "LEASE-L4-PERM",
                "run_id": "RUN-L4-PERM",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-perm-lease",
        )
    )

    class PermissionDenied(FakeAdapter):
        def execute(self, request: dict) -> dict:
            raise PermissionError("missing tool permission")

    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-PERM",
        adapter=PermissionDenied([]),
        worker_id="w1",
    )
    assert result.action == "paused_work_unit"
    wu = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu["status"] == "blocked"


def test_unmatched_decision_blocks_only_dependent_subgraph_and_morning_answer_resumes(
    workspace: Workspace,
) -> None:
    _seed_grant(
        workspace,
        "GRANT-L4-GRAPH",
        work_unit_ids=["WU-A", "WU-B", "WU-C"],
    )
    grant_path = workspace.ai_team / "run-authorization-grants" / "GRANT-L4-GRAPH.json"
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    grant["decision_menu"] = [
        {
            "id": "DM-L4-ANSWER",
            "trigger": {"type": "dependency_choice", "conditions": {"safe": True}},
            "scope": {"work_units": ["WU-A"]},
            "required_evidence": ["EV-L4"],
            "maximum_uses": 1,
            "uses_count": 0,
        }
    ]
    grant_path.write_text(json.dumps(grant), encoding="utf-8")
    gateway = CommandGateway(workspace)
    gateway.execute_command(
        _open_run(
            "RUN-L4-GRAPH",
            work_unit_ids=["WU-A", "WU-B", "WU-C"],
            grant_id="GRANT-L4-GRAPH",
        )
    )
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    _seed_work_unit(workspace, "WU-B", status="ready")
    _seed_work_unit(workspace, "WU-C", status="ready")
    dependent_path = workspace.ai_team / "work-units" / "WU-B.yaml"
    dependent = yaml.safe_load(dependent_path.read_text(encoding="utf-8"))
    dependent["dependencies"] = ["WU-A"]
    dependent_path.write_text(yaml.safe_dump(dependent), encoding="utf-8")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-GRAPH-A"},
            payload={
                "id": "LEASE-L4-GRAPH-A",
                "run_id": "RUN-L4-GRAPH",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-graph-lease",
        )
    )
    unresolved, unresolved_exit = gateway.execute_command(
        _envelope(
            "ResolveRunDecision",
            target={"kind": "run_decision", "id": "DECISION-L4-UNMATCHED"},
            payload={
                "run_id": "RUN-L4-GRAPH",
                "work_unit_id": "WU-A",
                "trigger": {"type": "unknown_fork"},
                "proposed_entry_id": "DM-NOT-FOUND",
                "evidence": [],
            },
            key="l4-graph-unmatched",
        )
    )
    assert unresolved_exit == 0
    assert unresolved["details"]["resolved"] is False

    independent = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-GRAPH",
        adapter=FakeAdapter([]),
        worker_id="w2",
    )
    assert independent.action == "started_work_unit"
    assert independent.work_unit_id == "WU-C"

    answered, answered_exit = gateway.execute_command(
        _envelope(
            "ResolveRunDecision",
            target={"kind": "run_decision", "id": "DECISION-L4-MORNING"},
            payload={
                "run_id": "RUN-L4-GRAPH",
                "work_unit_id": "WU-A",
                "trigger": {"type": "dependency_choice", "safe": True},
                "proposed_entry_id": "DM-L4-ANSWER",
                "evidence": ["EV-L4"],
            },
            key="l4-graph-morning",
        )
    )
    assert answered_exit == 0
    assert answered["details"]["resolved"] is True
    resumed = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-L4-GRAPH",
        adapter=FakeAdapter([]),
        worker_id="w1",
    )
    assert resumed.action == "reacquired_work_unit"
    assert resumed.work_unit_id == "WU-A"


def test_decision_proposal_from_adapter_is_validated_by_core(workspace: Workspace) -> None:
    _seed_grant(workspace, "GRANT-DECISION", work_unit_ids=["WU-A"])
    grant_path = workspace.ai_team / "run-authorization-grants" / "GRANT-DECISION.json"
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    grant["decision_menu"] = [
        {
            "id": "DM-PROP",
            "trigger": {
                "type": "dependency_choice",
                "package_category": "logging",
                "conditions": {"production_runtime": False},
            },
            "authorized_option": {"option_id": "use_existing"},
            "scope": {"work_units": ["WU-A"]},
            "required_evidence": ["license_check"],
            "maximum_uses": 1,
            "uses_count": 0,
        }
    ]
    grant_path.write_text(json.dumps(grant), encoding="utf-8")
    gateway = CommandGateway(workspace)
    gateway.execute_command(
        _open_run("RUN-DECISION", work_unit_ids=["WU-A"], grant_id="GRANT-DECISION")
    )
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-DECISION"},
            payload={
                "id": "LEASE-DECISION",
                "run_id": "RUN-DECISION",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="decision-lease",
        )
    )
    adapter = FakeAdapter(
        [
            {
                "status": "blocked",
                "summary": "fork encountered",
                "checks": [],
                "artifacts": [],
                "decision_proposal": {
                    "trigger": {
                        "type": "dependency_choice",
                        "package_category": "logging",
                        "conditions": {"production_runtime": False},
                    },
                    "proposed_entry_id": "DM-PROP",
                    "evidence": ["license_check"],
                },
            }
        ]
    )
    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-DECISION",
        adapter=adapter,
        worker_id="w1",
    )
    assert result.action == "decision_resolved"
    assert result.details["resolved"] is True


def test_risk_escalation_from_adapter_pauses_when_critical_wip_conflict(
    workspace: Workspace,
) -> None:
    """Document 6 §7.3/§11 — adapter-reported escalation is Core-applied; WIP=1 pauses."""
    _seed_grant(workspace, "GRANT-RISK-TICK", work_unit_ids=["WU-A", "WU-B"])
    gateway = CommandGateway(workspace)
    gateway.execute_command(
        _open_run(
            "RUN-RISK-TICK",
            work_unit_ids=["WU-A", "WU-B"],
            grant_id="GRANT-RISK-TICK",
        )
    )
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    _seed_work_unit(workspace, "WU-B", status="verification")
    other = workspace.ai_team / "work-units" / "WU-B.yaml"
    other_doc = yaml.safe_load(other.read_text(encoding="utf-8"))
    other_doc["risk"]["class"] = "critical"
    other.write_text(yaml.safe_dump(other_doc), encoding="utf-8")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-RISK"},
            payload={
                "id": "LEASE-RISK",
                "run_id": "RUN-RISK-TICK",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="risk-lease",
        )
    )
    adapter = FakeAdapter(
        [
            {
                **_succeeded_result("found secret exposure"),
                "risk_escalation": {
                    "new_risk_class": "critical",
                    "reason": "secret exposure discovered mid-implementation",
                },
            }
        ]
    )
    result = run_scheduling_tick(
        gateway,
        workspace,
        run_id="RUN-RISK-TICK",
        adapter=adapter,
        worker_id="w1",
    )
    assert result.action == "paused_for_risk_escalation"
    wu = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-A.yaml").read_text(encoding="utf-8")
    )
    assert wu["risk"]["class"] == "critical"
    assert wu["status"] == "waiting_decision"


def test_dispatch_request_includes_timeout_seconds(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-TIMEOUT", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-TIMEOUT"},
            payload={
                "id": "LEASE-L4-TIMEOUT",
                "run_id": "RUN-L4-TIMEOUT",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-timeout-lease",
        )
    )
    adapter = FakeAdapter([{"status": "timed_out", "summary": "slow"}])
    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-L4-TIMEOUT", adapter=adapter, worker_id="w1"
    )
    assert result.action == "recorded_attempt"
    assert "timeout_seconds" in adapter.requests[0]
    assert float(adapter.requests[0]["timeout_seconds"]) >= 1.0


def test_matching_implementation_timeouts_across_work_units_are_not_systemic(
    workspace: Workspace,
) -> None:
    _seed_grant(workspace, "GRANT-L4-SYS", work_unit_ids=["WU-A", "WU-B"])
    gateway = CommandGateway(workspace)
    gateway.execute_command(
        _open_run(
            "RUN-L4-SYS",
            work_unit_ids=["WU-A", "WU-B"],
            grant_id="GRANT-L4-SYS",
            maximum_parallel_workers=2,
        )
    )
    for work_unit_id in ("WU-A", "WU-B"):
        _seed_work_unit(workspace, work_unit_id, status="in_progress")
    for work_unit_id, lease_id in (("WU-A", "LEASE-L4-SYS-A"), ("WU-B", "LEASE-L4-SYS-B")):
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "AcquireWorkerLease",
                target={"kind": "worker_lease", "id": lease_id},
                payload={
                    "id": lease_id,
                    "run_id": "RUN-L4-SYS",
                    "work_unit_id": work_unit_id,
                    "worker_id": f"worker-{work_unit_id}",
                },
                key=f"l4-sys-{work_unit_id}",
            )
        )
        assert exit_code == 0, receipt.get("errors")

    timed_out = {"status": "timed_out", "summary": "same timeout every time"}
    for work_unit_id in ("WU-A", "WU-B"):
        result = run_scheduling_tick(
            gateway,
            workspace,
            run_id="RUN-L4-SYS",
            adapter=FakeAdapter([timed_out]),
            worker_id=f"worker-{work_unit_id}",
        )
        assert result.action == "recorded_attempt"
        assert result.work_unit_id == work_unit_id

    run = yaml.safe_load(
        (workspace.ai_team / "runs" / "RUN-L4-SYS.yaml").read_text(encoding="utf-8")
    )
    assert run["status"] == "active"
    attempts = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in (workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")
        if yaml.safe_load(path.read_text(encoding="utf-8")).get("status") == "timed_out"
    ]
    assert {item["work_unit_id"] for item in attempts} == {"WU-A", "WU-B"}
    assert all(item.get("failure_code") == "agent_timeout" for item in attempts)


def test_orphan_started_attempt_is_recovered_on_restart(workspace: Workspace) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-L4-ORPHAN", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    gateway.execute_command(
        _envelope(
            "AcquireWorkerLease",
            target={"kind": "worker_lease", "id": "LEASE-L4-ORPHAN"},
            payload={
                "id": "LEASE-L4-ORPHAN",
                "run_id": "RUN-L4-ORPHAN",
                "work_unit_id": "WU-A",
                "worker_id": "w1",
            },
            key="l4-orphan-lease",
        )
    )
    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt = {
        "id": "ATTEMPT-L4-ORPHAN",
        "revision": 1,
        "run_id": "RUN-L4-ORPHAN",
        "execution_id": "EXE-L4-ORPHAN",
        "work_unit_id": "WU-A",
        "worker_lease_id": "LEASE-L4-ORPHAN",
        "epoch": 1,
        "step": "sandbox_implementation",
        "status": "started",
        "started_at": "2026-08-30T00:00:00+00:00",
        "ended_at": None,
        "summary": None,
        "checks": [],
        "artifacts": [],
        "workspace": {},
        "contract": {},
        "requested_commands": [],
        "usage": {},
        "provider": {},
    }
    (attempts_dir / "ATTEMPT-L4-ORPHAN.yaml").write_text(
        yaml.safe_dump(attempt), encoding="utf-8"
    )
    _expire_lease_heartbeat(workspace, "LEASE-L4-ORPHAN")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-L4-ORPHAN", adapter=FakeAdapter([]), worker_id="w1"
    )
    recovered = yaml.safe_load(
        (attempts_dir / "ATTEMPT-L4-ORPHAN.yaml").read_text(encoding="utf-8")
    )
    assert recovered["status"] == "timed_out"
    assert recovered["failure_code"] == "orphan_started"
    assert recovered["failure_scope"] == "run"
    assert result.action in {"reassigned_lease", "recorded_attempt", "idle", "started_work_unit"}


def test_tick_propagates_context_package_ref_on_execution_request(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-CTX-OK", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="ready")
    adapter = FakeAdapter([_succeeded_result()])

    started = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-OK", adapter=adapter, worker_id="w1"
    )
    assert started.action == "started_work_unit"
    executed = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-OK", adapter=adapter, worker_id="w1"
    )
    assert executed.action in {"advanced_work_unit", "recorded_attempt"}
    assert adapter.requests
    assert adapter.requests[0]["context_package_ref"] == (
        ".ai-team/context-packages/CTX-WU-A.yaml"
    )


def test_tick_blocks_implementation_when_context_package_missing(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-CTX-MISS", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="ready", context_package_ref=False)
    adapter = FakeAdapter([_succeeded_result()])

    started = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-MISS", adapter=adapter, worker_id="w1"
    )
    assert started.action == "started_work_unit"
    blocked = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-MISS", adapter=adapter, worker_id="w1"
    )
    assert blocked.action in {"recorded_attempt", "advanced_work_unit", "paused_work_unit"}
    assert adapter.requests == []
    attempt = yaml.safe_load(
        next((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")).read_text(
            encoding="utf-8"
        )
    )
    assert attempt["status"] == "blocked"
    assert "context_package" in str(attempt.get("summary") or "")


def test_tick_blocks_when_required_shared_contract_missing_from_context(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-CTX-CONTRACT", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="ready")
    packages = workspace.ai_team / "context-packages"
    ctx_path = packages / "CTX-WU-A.yaml"
    document = yaml.safe_load(ctx_path.read_text(encoding="utf-8"))
    document["required_contracts"] = ["contracts/shared/api-v1.json"]
    document["completeness_status"] = "incomplete"
    document["missing_inputs"] = ["contracts/shared/api-v1.json"]
    ctx_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    adapter = FakeAdapter([_succeeded_result()])

    started = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-CONTRACT", adapter=adapter, worker_id="w1"
    )
    assert started.action == "started_work_unit"
    blocked = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-CONTRACT", adapter=adapter, worker_id="w1"
    )
    assert blocked.action == "paused_work_unit"
    assert adapter.requests == []
    attempt = yaml.safe_load(
        next((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")).read_text(
            encoding="utf-8"
        )
    )
    assert attempt["status"] == "blocked"
    assert "incomplete" in str(attempt.get("summary") or "")


def test_orphan_started_attempt_recovers_when_lease_document_is_gone(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-ORPHAN-GONE", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="in_progress")
    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt = {
        "id": "ATTEMPT-ORPHAN-GONE",
        "revision": 1,
        "run_id": "RUN-ORPHAN-GONE",
        "execution_id": "EXE-ORPHAN-GONE",
        "work_unit_id": "WU-A",
        "worker_lease_id": "LEASE-GONE",
        "epoch": 1,
        "step": "sandbox_implementation",
        "status": "started",
        "started_at": "2026-08-30T00:00:00+00:00",
        "ended_at": None,
        "summary": None,
        "checks": [],
        "artifacts": [],
        "workspace": {},
        "contract": {},
        "requested_commands": [],
        "usage": {},
        "provider": {},
    }
    (attempts_dir / "ATTEMPT-ORPHAN-GONE.yaml").write_text(
        yaml.safe_dump(attempt), encoding="utf-8"
    )
    # No lease file and no leases_by_work_unit entry — the failure mode from audit.
    run_path = workspace.ai_team / "runs" / "RUN-ORPHAN-GONE.yaml"
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    run_document["leases_by_work_unit"] = {}
    run_path.write_text(yaml.safe_dump(run_document), encoding="utf-8")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-ORPHAN-GONE", adapter=FakeAdapter([]), worker_id="w1"
    )
    recovered = yaml.safe_load(
        (attempts_dir / "ATTEMPT-ORPHAN-GONE.yaml").read_text(encoding="utf-8")
    )
    assert recovered["status"] == "timed_out"
    assert recovered["failure_code"] == "orphan_started"
    assert result.action != "idle" or recovered["status"] == "timed_out"


def test_tick_signals_awaiting_human_for_blocked_plus_human_test_mix(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-HUMAN-MIX", work_unit_ids=["WU-A", "WU-B"]))
    _seed_work_unit(workspace, "WU-A", status="blocked")
    _seed_work_unit(workspace, "WU-B", status="human_test")

    result = run_scheduling_tick(
        gateway, workspace, run_id="RUN-HUMAN-MIX", adapter=FakeAdapter([]), worker_id="w1"
    )
    assert result.action == "awaiting_human"
    assert "WU-B" in result.details["waiting_work_unit_ids"]
    run_document = yaml.safe_load(
        (workspace.ai_team / "runs" / "RUN-HUMAN-MIX.yaml").read_text(encoding="utf-8")
    )
    assert run_document["status"] == "active"


def test_context_package_ref_rejects_path_escape(workspace: Workspace) -> None:
    from governed_ai.core.orchestrator.tick import _canonical_context_package_path

    with pytest.raises(ValueError, match="context-packages|\\.\\."):
        _canonical_context_package_path(workspace, "../secrets/creds.yaml")
    with pytest.raises(ValueError, match="relative|context-packages"):
        _canonical_context_package_path(workspace, r"C:\Windows\system32\drivers\etc\hosts")


def test_tick_blocks_when_context_package_fails_schema_or_role_mismatch(
    workspace: Workspace,
) -> None:
    gateway = CommandGateway(workspace)
    gateway.execute_command(_open_run("RUN-CTX-SCHEMA", work_unit_ids=["WU-A"]))
    _seed_work_unit(workspace, "WU-A", status="ready")
    packages = workspace.ai_team / "context-packages"
    # Schema-invalid: only id — missing work_unit, role, items.
    (packages / "CTX-WU-A.yaml").write_text("id: CTX-WU-A\n", encoding="utf-8")
    adapter = FakeAdapter([_succeeded_result()])

    started = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-SCHEMA", adapter=adapter, worker_id="w1"
    )
    assert started.action == "started_work_unit"
    blocked = run_scheduling_tick(
        gateway, workspace, run_id="RUN-CTX-SCHEMA", adapter=adapter, worker_id="w1"
    )
    assert blocked.action == "paused_work_unit"
    assert adapter.requests == []
    attempt = yaml.safe_load(
        next((workspace.ai_team / "runs" / "execution-attempts").glob("*.yaml")).read_text(
            encoding="utf-8"
        )
    )
    assert attempt["status"] == "blocked"
    assert "schema" in str(attempt.get("summary") or "").lower()
