"""Tests for the Agent Execution Gateway (EXEC-GATEWAY-AC-*)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from governed_ai.core.execution_gateway.capabilities import (
    assert_capabilities,
    build_capability_descriptor,
)
from governed_ai.core.execution_gateway.check_registry import (
    normalize_check_name,
    resolve_required_checks,
)
from governed_ai.core.execution_gateway.context import assert_context_hash, compile_context_package
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError
from governed_ai.core.execution_gateway.evidence import sha256_file, verify_artifact
from governed_ai.core.execution_gateway.gateway import AgentExecutionGateway
from governed_ai.core.execution_gateway.legacy import LegacyExecutionResultAdapter
from governed_ai.core.execution_gateway.role_resolver import resolve_role
from governed_ai.core.execution_gateway.scope import compute_effective_scope
from governed_ai.core.execution_gateway.security import (
    assert_command_allowed,
    assert_no_escaping_link,
    assert_not_control_plane,
    assert_relative_workspace_path,
    redact_secrets,
)
from governed_ai.core.execution_gateway.transactional import assert_epoch_fencing
from governed_ai.core.execution_gateway.verification import run_verification_command
from governed_ai.core.supervisor.daemon import SupervisorDaemon
from governed_ai.core.supervisor.paths import ensure_supervisor_layout
from governed_ai.core.workspace import Workspace


def _git_init(root: Path) -> str:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("base\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return sha


def _workspace(tmp_path: Path) -> tuple[Workspace, str]:
    sha = _git_init(tmp_path)
    ai_team = tmp_path / ".ai-team"
    (ai_team / "runs").mkdir(parents=True)
    (ai_team / "work-units").mkdir(parents=True)
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "evidence").mkdir(parents=True)
    (ai_team / "project-profile.yaml").write_text(
        "project:\n  id: test\n  repository_kind: client_project\n"
        "commands:\n  unit_test: python -c \"print('ok')\"\n",
        encoding="utf-8",
    )
    ensure_supervisor_layout(ai_team)
    return Workspace.from_root(tmp_path), sha


def _capabilities(**overrides: Any) -> dict[str, Any]:
    base = build_capability_descriptor(
        adapter_id="fake",
        adapter_version="1.0.0",
        supported_protocol_versions=["1.0"],
        supported_roles=["backend-developer", "frontend-developer", "qa-test"],
        supported_procedures=["implement-work-unit", "webapp-testing"],
        isolated_workspace=True,
        cancellation=True,
        progress_events=True,
        structured_output=True,
        command_enforcement=True,
        filesystem_enforcement=True,
        maximum_parallelism=1,
    )
    base.update(overrides)
    return base


def _request(sha: str, **overrides: Any) -> dict[str, Any]:
    ctx_hash = "sha256:" + ("ab" * 32)
    base = {
        "schema_version": 1,
        "execution_id": "EXE-1",
        "run_id": "RUN-1",
        "work_unit_id": "WU-A",
        "lease_id": "LEASE-1",
        "epoch": 1,
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "base_sha": sha,
        "context_package_hash": ctx_hash,
        "contract": {
            "schema_version": 1,
            "role_id": "backend-developer",
            "procedure_id": "implement-work-unit",
            "required_checks": ["implementation"],
            "allowed_shell_commands": ['python -c "print(\'ok\')"'],
            "accessible_secrets": [],
            "context_package_hash": ctx_hash,
            "effective_scope": ["src/**"],
        },
        "adapter_id": "fake",
    }
    base.update(overrides)
    return base


class FakeProductAdapter:
    """Writes an allowed product file and returns agent-reported evidence."""

    def __init__(self, *, hostile: bool = False, bad_hash: bool = False) -> None:
        self.hostile = hostile
        self.bad_hash = bad_hash

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        root = Path(str(request.get("execution_workspace") or "."))
        product = root / "src" / "app.py"
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_text("print('updated')\n", encoding="utf-8")
        evidence = root / ".ai-team" / "evidence" / "WU-A" / "note.txt"
        if self.hostile:
            banned = root / ".ai-team" / "state" / "project-state.yaml"
            banned.parent.mkdir(parents=True, exist_ok=True)
            banned.write_text("phase: hacked\n", encoding="utf-8")
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("done\n", encoding="utf-8")
        digest = sha256_file(evidence)
        if self.bad_hash:
            digest = "sha256:" + ("00" * 32)
        return {
            "schema_version": 1,
            "execution_id": request["execution_id"],
            "run_id": request["run_id"],
            "work_unit_id": request["work_unit_id"],
            "lease_id": request["lease_id"],
            "epoch": request["epoch"],
            "role_id": request["role_id"],
            "procedure_id": request["procedure_id"],
            "status": "succeeded",
            "summary": "updated app",
            "checks": [
                {
                    "canonical_id": "implementation",
                    "reported_name": "implementation",
                    "status": "passed",
                    "blocking": True,
                    "trust_level": "agent_reported",
                    "evidence_ref": evidence.as_posix(),
                }
            ],
            "artifacts": [
                {
                    "kind": "file",
                    "path": evidence.relative_to(root).as_posix(),
                    "agent_reported_sha256": digest,
                }
            ],
            "requested_commands": [],
            "limitations": [],
            "workspace": {
                "base_sha": request["base_sha"],
                "claimed_result_sha": request["base_sha"],
            },
            "usage": {},
            "provider_metadata": {},
            "context_package_hash": request["context_package_hash"],
        }


def test_identity_mismatch_refused(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    adapter = LegacyExecutionResultAdapter()
    request = _request(sha)
    raw = {
        "schema_version": 1,
        "execution_id": "EXE-1",
        "run_id": "RUN-OTHER",
        "work_unit_id": "WU-A",
        "lease_id": "LEASE-1",
        "epoch": 1,
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "status": "succeeded",
        "summary": "x",
        "checks": [],
        "artifacts": [],
        "workspace": {},
    }
    with pytest.raises(ExecutionGatewayError) as exc:
        adapter.adapt(raw, request=request)
    assert exc.value.code == "identity_mismatch"


def test_check_alias_normalization() -> None:
    assert normalize_check_name("mvn-test-failsafe") == "tests"
    assert normalize_check_name("pytest") == "tests"
    assert normalize_check_name("audit_release") == "audit"
    assert normalize_check_name("audit-release") == "audit"
    satisfied, rejected, missing = resolve_required_checks(
        ["mvn-test-failsafe"], required=["tests"]
    )
    assert "tests" in satisfied
    assert not missing
    assert not rejected


def test_unknown_alias_never_satisfies() -> None:
    satisfied, rejected, missing = resolve_required_checks(
        ["totally-invented-check"], required=["tests"]
    )
    assert "tests" not in satisfied
    assert rejected == ["totally-invented-check"]
    assert missing == ["tests"]


def test_ac_descriptive_and_ranges() -> None:
    assert normalize_check_name("AC-WU-01 first scenario") == "AC-WU-01"
    satisfied, _, missing = resolve_required_checks(
        ["AC-INV-04-01..05"],
        required=["AC-INV-04-03"],
    )
    assert "AC-INV-04-03" in satisfied
    assert not missing


def test_artifact_hash_recalculated(tmp_path: Path) -> None:
    workspace, _sha = _workspace(tmp_path)
    path = workspace.root / "src" / "app.py"
    observed = verify_artifact(
        workspace.root,
        path="src/app.py",
        agent_reported_sha256=sha256_file(path),
        max_bytes=1024 * 1024,
    )
    assert observed["trust_level"] == "framework_verified"
    with pytest.raises(ExecutionGatewayError) as exc:
        verify_artifact(
            workspace.root,
            path="src/app.py",
            agent_reported_sha256="sha256:" + ("11" * 32),
            max_bytes=1024 * 1024,
        )
    assert exc.value.code == "artifact_hash_mismatch"


def test_result_sha_mismatch_refused(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    compiled, _context = gateway.compile_request(
        execution_id="EXE-1",
        run_id="RUN-1",
        work_unit=work_unit,
        lease_id="LEASE-1",
        epoch=1,
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        base_sha=sha,
        grant_allowed_paths=["src/**"],
        allowed_shell_commands=[],
        required_checks=["implementation"],
        capabilities=_capabilities(),
    )

    class _Adapter:
        def execute(self, request: dict[str, Any]) -> dict[str, Any]:
            # Mutate project root (non-ephemeral) and claim a fake SHA.
            root = workspace.root
            request = {**request, "execution_workspace": str(root)}
            result = FakeProductAdapter().execute(request)
            result["workspace"]["claimed_result_sha"] = "b" * 40
            return result

    outcome = gateway.execute(
        request=compiled,
        adapter=_Adapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**"],
        use_ephemeral_workspace=False,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "result_sha_mismatch"


def test_context_hash_mismatch() -> None:
    with pytest.raises(ExecutionGatewayError) as exc:
        assert_context_hash("sha256:dead", "sha256:beef")
    assert exc.value.code == "context_hash_mismatch"


def test_frontend_role_not_silently_backend() -> None:
    with pytest.raises(ExecutionGatewayError) as exc:
        resolve_role(
            work_unit={"zone": {"area": "frontend"}},
            fallback_role="backend-developer",
            allowed_roles=frozenset({"backend-developer"}),
        )
    assert exc.value.code == "unsupported_role"
    role = resolve_role(
        work_unit={
            "zone": {"area": "frontend"},
            "staffing_proposal": {"primary_role": "frontend-developer"},
        }
    )
    assert role == "frontend-developer"


def test_missing_capability_refused_before_launch() -> None:
    caps = _capabilities(supported_roles=["qa-test"])
    with pytest.raises(ExecutionGatewayError) as exc:
        assert_capabilities(
            caps,
            role_id="backend-developer",
            procedure_id="implement-work-unit",
        )
    assert exc.value.code == "unsupported_role"


def test_empty_and_contradictory_scope() -> None:
    with pytest.raises(ExecutionGatewayError) as exc:
        compute_effective_scope(
            work_unit={"scope": {"include": [".ai-team/state/**"], "exclude": []}},
            grant_allowed_paths=["src/**"],
        )
    assert exc.value.code == "forbidden_control_plane_path"

    with pytest.raises(ExecutionGatewayError) as exc2:
        compute_effective_scope(
            work_unit={"scope": {"include": ["frontend/**"], "exclude": []}},
            grant_allowed_paths=["backend/**"],
        )
    assert exc2.value.code == "contradictory_path_policy"


def test_compile_request_resolves_role_write_paths_into_effective_scope(
    tmp_path: Path,
) -> None:
    """Document 12 §2.2: contract.effective_scope must be role-resolved, not
    the raw Work Unit scope — this is compile_request's role_write_paths axis,
    fed by resolve_role_write_paths (see test_role_write_paths_resolution.py).
    A qa-test-style role narrows an otherwise-broader WU/grant scope down to
    just its own declared writable area."""
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "title": "Update app",
        "scope": {"include": ["src/**", "tests/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _context = gateway.compile_request(
        execution_id="EXE-ROLE-SCOPE",
        run_id="RUN-1",
        work_unit=work_unit,
        lease_id="LEASE-1",
        epoch=1,
        role_id="qa-test",
        procedure_id="webapp-testing",
        base_sha=sha,
        grant_allowed_paths=["src/**", "tests/**"],
        allowed_shell_commands=[],
        required_checks=["tests"],
        capabilities=_capabilities(),
        role_write_paths=["tests/"],
    )
    assert request["contract"]["effective_scope"] == ["tests/**"]


def test_control_plane_and_traversal(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    with pytest.raises(ExecutionGatewayError):
        assert_not_control_plane(".ai-team/state/project-state.yaml")
    with pytest.raises(ExecutionGatewayError):
        assert_relative_workspace_path(workspace.root, "../outside.txt")
    with pytest.raises(ExecutionGatewayError):
        assert_relative_workspace_path(workspace.root, str(tmp_path / "abs.py"))


def test_escaping_symlink(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.write_text("secret\n", encoding="utf-8")
    link = workspace.root / "src" / "leak"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    with pytest.raises(ExecutionGatewayError) as exc:
        assert_no_escaping_link(workspace.root, "src/leak")
    assert exc.value.code == "escaping_symlink_or_junction"


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions only")
def test_escaping_junction_windows(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    outside = tmp_path.parent / f"junc-outside-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    (outside / "x.txt").write_text("x\n", encoding="utf-8")
    target = workspace.root / "src" / "junc"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"mklink /J unavailable: {completed.stderr}")
    with pytest.raises(ExecutionGatewayError) as exc:
        assert_no_escaping_link(workspace.root, "src/junc")
    assert exc.value.code == "escaping_symlink_or_junction"


def test_unauthorized_command_and_secret_redaction() -> None:
    with pytest.raises(ExecutionGatewayError):
        assert_command_allowed("git push origin main", ["python"])
    with pytest.raises(ExecutionGatewayError):
        assert_command_allowed("rm -rf /", ["python"])
    assert "***REDACTED***" in redact_secrets("token=super-secret", ["super-secret"])


def test_verification_timeout_and_hash(tmp_path: Path) -> None:
    import sys

    workspace, _ = _workspace(tmp_path)
    script = tmp_path / "sleep_long.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    command = f"{sys.executable} {script}"
    result = run_verification_command(
        workspace_root=workspace.root,
        command=command,
        allowlist=[command],
        timeout_seconds=0.2,
        secrets_to_redact=["secret-value"],
        canonical_check_id="tests",
    )
    assert result["status"] == "timed_out"
    assert result["trust_level"] == "framework_verified"
    assert result["transcript_hash"]


def test_stale_epoch_refused() -> None:
    with pytest.raises(ExecutionGatewayError) as exc:
        assert_epoch_fencing(request_epoch=2, result_epoch=1)
    assert exc.value.code == "stale_epoch"


def test_happy_path_governed_commit(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "title": "Update app",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, context = gateway.compile_request(
        execution_id="EXE-HAPPY",
        run_id="RUN-1",
        work_unit=work_unit,
        lease_id="LEASE-1",
        epoch=3,
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        base_sha=sha,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        allowed_shell_commands=[],
        required_checks=["implementation"],
        capabilities=_capabilities(),
    )
    assert context["context_package_hash"]
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.ok, outcome.error
    assert outcome.promoted_sha
    assert outcome.result is not None
    assert outcome.result["workspace"]["resumable"] is True
    assert outcome.result["workspace"]["trust_level"] == "framework_verified"


def test_hostile_no_promoted_commit(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = gateway.compile_request(
        execution_id="EXE-HOSTILE",
        run_id="RUN-1",
        work_unit=work_unit,
        lease_id="LEASE-1",
        epoch=1,
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        base_sha=sha,
        grant_allowed_paths=["src/**"],
        allowed_shell_commands=[],
        required_checks=["implementation"],
        capabilities=_capabilities(),
    )
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(hostile=True, bad_hash=True),
        work_unit=work_unit,
        grant_allowed_paths=["src/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    quarantine = workspace.ai_team / "supervisor" / "quarantine" / "EXE-HOSTILE"
    assert quarantine.is_dir()
    # Healthy base SHA preserved — no promotion registry entry.
    assert not (workspace.ai_team / "supervisor" / "promotions" / "EXE-HOSTILE.json").is_file()


def test_legacy_adapter_compat(tmp_path: Path) -> None:
    _, sha = _workspace(tmp_path)
    request = _request(sha)
    raw = {
        "protocol_version": "1.0",
        "execution_id": "EXE-1",
        "status": "succeeded",
        "summary": "legacy handoff",
        "checks": [{"name": "pytest", "status": "passed", "evidence_ref": "e1"}],
        "artifacts": [{"kind": "file", "path": "src/app.py", "sha256": "sha256:" + ("aa" * 32)}],
        "workspace": {"base_sha": sha, "result_sha": sha},
        "contract": {
            "role_id": "backend-developer",
            "procedure_id": "implement-work-unit",
        },
    }
    adapted = LegacyExecutionResultAdapter().adapt(raw, request=request)
    assert adapted["run_id"] == "RUN-1"
    assert adapted["checks"][0]["canonical_id"] == "tests"
    assert adapted["checks"][0]["trust_level"] == "agent_reported"


def test_supervisor_uses_gateway(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    gateway = AgentExecutionGateway(workspace)
    request, _ = gateway.compile_request(
        execution_id="EXE-DAEMON",
        run_id="RUN-1",
        work_unit=work_unit,
        lease_id="LEASE-1",
        epoch=1,
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        base_sha=sha,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        allowed_shell_commands=[],
        required_checks=["implementation"],
        capabilities=_capabilities(),
    )
    daemon = SupervisorDaemon(workspace, interval_seconds=0.05)
    daemon.acquire()
    try:
        outcome = daemon.accept_execution(
            request=request,
            adapter=FakeProductAdapter(),
            work_unit=work_unit,
            grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
            use_ephemeral_workspace=True,
            run_independent_verification=False,
        )
        assert outcome.ok
        assert outcome.promoted_sha
    finally:
        daemon.shutdown()


def test_tick_uses_registry_aliases() -> None:
    from governed_ai.core.orchestrator.tick import _check_matches_required

    assert _check_matches_required("mvn-test-failsafe", "tests")
    assert _check_matches_required("audit_release", "audit")
    assert not _check_matches_required("random-pass", "tests")


def test_compile_context_package_hash_stable() -> None:
    package = compile_context_package(
        contract={"role_id": "backend-developer"},
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        work_unit={"id": "WU-A", "title": "t"},
        acceptance_criteria=[],
        required_checks=["implementation"],
        effective_scope={"include": ["src/**"]},
    )
    again = compile_context_package(
        contract={"role_id": "backend-developer"},
        role_id="backend-developer",
        procedure_id="implement-work-unit",
        work_unit={"id": "WU-A", "title": "t"},
        acceptance_criteria=[],
        required_checks=["implementation"],
        effective_scope={"include": ["src/**"]},
    )
    assert package["context_package_hash"] == again["context_package_hash"]


# ---------------------------------------------------------------------------
# EXEC-GATEWAY-AC acceptance coverage (strict guarantees)
# ---------------------------------------------------------------------------


def _compile(gateway: AgentExecutionGateway, sha: str, work_unit: dict[str, Any], **kwargs: Any):
    params = {
        "execution_id": "EXE-1",
        "run_id": "RUN-1",
        "work_unit": work_unit,
        "lease_id": "LEASE-1",
        "epoch": 1,
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "base_sha": sha,
        "grant_allowed_paths": ["src/**", ".ai-team/evidence/WU-A/**"],
        "allowed_shell_commands": [],
        "required_checks": ["implementation"],
        "capabilities": _capabilities(),
    }
    params.update(kwargs)
    return gateway.compile_request(**params)


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_id", "EXE-OTHER"),
        ("run_id", "RUN-OTHER"),
        ("work_unit_id", "WU-OTHER"),
        ("lease_id", "LEASE-OTHER"),
        ("epoch", 99),
        ("role_id", "frontend-developer"),
        ("procedure_id", "webapp-testing"),
    ],
)
def test_ac01_identity_mismatch_each_field(tmp_path: Path, field: str, value: Any) -> None:
    """EXEC-GATEWAY-AC-01 — each identity field mismatch is refused."""
    _, sha = _workspace(tmp_path)
    adapter = LegacyExecutionResultAdapter()
    request = _request(sha)
    request["contract"] = {
        **request["contract"],
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
    }
    raw = FakeProductAdapter().execute({**request, "execution_workspace": str(tmp_path)})
    raw[field] = value
    with pytest.raises(ExecutionGatewayError) as exc:
        adapter.adapt(raw, request=request)
    assert exc.value.code == "identity_mismatch"


def test_ac02_strict_validation_valid_and_invalid() -> None:
    """EXEC-GATEWAY-AC-02 — strict runtime validation for contracts/results."""
    from governed_ai.core.execution_gateway.validation import (
        validate_execution_request,
        validate_execution_result,
    )

    good = _request("a" * 40)
    good["contract"] = {
        **good["contract"],
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "required_checks": ["implementation"],
        "allowed_shell_commands": [],
        "effective_scope": ["src/**"],
    }
    assert validate_execution_request(good) == []

    bad = dict(good)
    bad["epoch"] = "not-an-int"
    errors = validate_execution_request(bad)
    assert any(item.code == "invalid_type" for item in errors)

    result = {
        "schema_version": 1,
        "execution_id": "EXE-1",
        "run_id": "RUN-1",
        "work_unit_id": "WU-A",
        "lease_id": "LEASE-1",
        "epoch": 1,
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "status": "succeeded",
        "summary": "ok",
        "checks": [],
        "artifacts": [],
        "requested_commands": [],
        "limitations": [],
        "workspace": {
            "schema_version": 1,
            "base_sha": "a" * 40,
            "claimed_result_sha": None,
            "observed_head_sha": None,
            "promoted_sha": None,
            "trust_level": "agent_reported",
            "resumable": False,
        },
        "usage": {},
        "provider_metadata": {},
        "context_package_hash": "sha256:" + ("ab" * 32),
    }
    assert validate_execution_result(result) == []
    result_bad = dict(result)
    result_bad["status"] = "not-a-status"
    assert any(item.code == "invalid_enum" for item in validate_execution_result(result_bad))


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "1"),
        ("epoch", "1"),
        ("epoch", 1.0),
        ("epoch", True),
        ("summary", 1),
        ("checks", {}),
        ("artifacts", {}),
        ("requested_commands", {}),
        ("limitations", {}),
        ("workspace", []),
        ("usage", []),
        ("provider_metadata", []),
        ("context_package_hash", "sha256:not-a-digest"),
    ],
)
def test_ac02_result_fields_reject_wrong_exact_types(field: str, value: Any) -> None:
    from governed_ai.core.execution_gateway.validation import validate_execution_result

    result = {
        "schema_version": 1,
        "execution_id": "EXE-1",
        "run_id": "RUN-1",
        "work_unit_id": "WU-A",
        "lease_id": "LEASE-1",
        "epoch": 1,
        "role_id": "backend-developer",
        "procedure_id": "implement-work-unit",
        "status": "succeeded",
        "summary": "ok",
        "checks": [],
        "artifacts": [],
        "requested_commands": [],
        "limitations": [],
        "workspace": {
            "schema_version": 1,
            "base_sha": "a" * 40,
            "claimed_result_sha": None,
            "observed_head_sha": None,
            "promoted_sha": None,
            "trust_level": "agent_reported",
            "resumable": False,
        },
        "usage": {},
        "provider_metadata": {},
        "context_package_hash": "sha256:" + ("ab" * 32),
    }
    result[field] = value
    assert validate_execution_result(result), field


@pytest.mark.parametrize(
    "status",
    ["failed", "blocked", "cancelled", "timed_out", "rejected"],
)
def test_ac02_non_succeeded_status_never_promoted(tmp_path: Path, status: str) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit)

    class _StatusAdapter:
        def execute(self, req: dict[str, Any]) -> dict[str, Any]:
            payload = FakeProductAdapter().execute(req)
            payload["status"] = status
            return payload

    outcome = gateway.execute(
        request=request,
        adapter=_StatusAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert outcome.error is not None
    assert outcome.error.code == "agent_status_not_succeeded"


def test_ac03_fake_sha_ephemeral_refused(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-03 — fake 40-char SHA rejected in default ephemeral mode."""
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit)

    class _FakeSha:
        def execute(self, req: dict[str, Any]) -> dict[str, Any]:
            payload = FakeProductAdapter().execute(req)
            payload["workspace"]["claimed_result_sha"] = "b" * 40
            return payload

    outcome = gateway.execute(
        request=request,
        adapter=_FakeSha(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert outcome.error is not None
    assert outcome.error.code == "result_sha_mismatch"


def test_ac04_context_hash_recalculated_from_compile(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-04 — compile_request hash equals recalculation of package bytes."""
    from governed_ai.core.execution_gateway.context import hash_context_package

    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "title": "t",
        "scope": {"include": ["src/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, context = _compile(gateway, sha, work_unit, grant_allowed_paths=["src/**"])
    assert hash_context_package(context) == context["context_package_hash"]
    assert request["context_package_hash"] == context["context_package_hash"]
    # Mutating the live contract after compile must not change the package hash.
    request["contract"]["role_id"] = "tampered"
    assert hash_context_package(context) == context["context_package_hash"]


def test_ac05_stale_epoch_against_authoritative_lease(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-05 — epoch N result refused after lease reassigned to N+1."""
    workspace, sha = _workspace(tmp_path)
    leases = workspace.ai_team / "runs" / "leases"
    leases.mkdir(parents=True, exist_ok=True)
    runs = workspace.ai_team / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "RUN-1.yaml").write_text(
        "id: RUN-1\nrevision: 1\nleases_by_work_unit:\n  WU-A:\n    lease_id: LEASE-NEW\n    epoch: 2\n",
        encoding="utf-8",
    )
    (leases / "LEASE-1.yaml").write_text(
        "id: LEASE-1\nstatus: superseded\nepoch: 1\nworker_id: old\n",
        encoding="utf-8",
    )
    (leases / "LEASE-NEW.yaml").write_text(
        "id: LEASE-NEW\nstatus: active\nepoch: 2\nworker_id: new\n",
        encoding="utf-8",
    )
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit, lease_id="LEASE-1", epoch=1)
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
        fence_authoritative_lease=True,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert outcome.error is not None
    assert outcome.error.code == "stale_epoch"
    assert not (workspace.ai_team / "supervisor" / "promotions" / "EXE-1.json").is_file()
    persisted = workspace.ai_team / "evidence" / "WU-A"
    assert not persisted.is_dir() or not list(persisted.glob("EVD-*.json"))


def test_ac06_scope_parent_child_both_orders() -> None:
    """EXEC-GATEWAY-AC-06 — intersection keeps only the most restrictive pattern."""
    wu_parent = {"scope": {"include": ["src/**"], "exclude": []}}
    scope_a = compute_effective_scope(
        work_unit=wu_parent,
        grant_allowed_paths=["src/restricted/**"],
    )
    assert scope_a["include"] == ["src/restricted/**"]

    wu_child = {"scope": {"include": ["src/restricted/**"], "exclude": []}}
    scope_b = compute_effective_scope(
        work_unit=wu_child,
        grant_allowed_paths=["src/**"],
    )
    assert scope_b["include"] == ["src/restricted/**"]

    with pytest.raises(ExecutionGatewayError) as exc:
        compute_effective_scope(
            work_unit={"scope": {"include": ["src/**"], "exclude": []}},
            grant_allowed_paths=[],
        )
    assert exc.value.code == "empty_effective_scope"


def test_ac07_role_procedure_combination_not_cartesian() -> None:
    """EXEC-GATEWAY-AC-07 — separate lists are not a Cartesian product proof."""
    from governed_ai.core.execution_gateway.role_resolver import assert_role_procedure

    with pytest.raises(ExecutionGatewayError):
        assert_role_procedure(
            role_id="backend-developer",
            procedure_id="webapp-testing",
            known_roles={"backend-developer", "qa-test"},
            role_procedures={"backend-developer": {"implement-work-unit"}, "qa-test": {"webapp-testing"}},
        )
    with pytest.raises(ExecutionGatewayError):
        assert_role_procedure(
            role_id="backend-developer",
            procedure_id="implement-work-unit",
            known_roles={"backend-developer"},
            supported_combinations={("qa-test", "webapp-testing")},
        )


def test_ac08_missing_capability_refused(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {"id": "WU-A", "scope": {"include": ["src/**"], "exclude": []}}
    with pytest.raises(ExecutionGatewayError) as exc:
        _compile(
            gateway,
            sha,
            work_unit,
            grant_allowed_paths=["src/**"],
            capabilities=_capabilities(supported_roles=["qa-test"], supported_procedures=["webapp-testing"]),
        )
    assert exc.value.code in {"unsupported_role", "unsupported_procedure", "missing_field"}


def test_ac09_unauthorized_requested_commands(tmp_path: Path) -> None:
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit)

    class _BadCmds:
        def execute(self, req: dict[str, Any]) -> dict[str, Any]:
            payload = FakeProductAdapter().execute(req)
            payload["requested_commands"] = ["git push origin main"]
            return payload

    outcome = gateway.execute(
        request=request,
        adapter=_BadCmds(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "unauthorized_command"

    with pytest.raises(ExecutionGatewayError):
        assert_command_allowed("cmd /c echo hi", ["echo"])
    with pytest.raises(ExecutionGatewayError):
        assert_command_allowed("python && rm -rf /", ["python"])


@pytest.mark.skipif(os.name != "nt", reason="Windows argv / shell=False specifics")
def test_ac09_windows_verification_shell_false(tmp_path: Path) -> None:
    import sys

    from governed_ai.core.execution_gateway.verification import compile_command_argv

    workspace, _ = _workspace(tmp_path)
    command = f"{sys.executable} -c print(1)"
    argv = compile_command_argv(command)
    assert argv[0] == sys.executable
    assert all(isinstance(part, str) for part in argv)
    result = run_verification_command(
        workspace_root=workspace.root,
        command=command,
        allowlist=[command],
        timeout_seconds=10,
        canonical_check_id="tests",
    )
    assert result["status"] == "passed"
    assert result["exit_code"] == 0


def test_ac10_artifact_mutated_after_verification(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-10 — verification command mutating artifacts blocks promotion."""
    import sys

    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    script = tmp_path / "mutate_after_verify.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('src/app.py').write_text('mutated-after-verify\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    mutate = f"{sys.executable} {script}"
    request, _ = _compile(
        gateway,
        sha,
        work_unit,
        allowed_shell_commands=[mutate],
        required_checks=["implementation"],
    )
    profile = {"commands": {"unit_test": mutate}}
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        profile=profile,
        use_ephemeral_workspace=True,
        run_independent_verification=True,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert outcome.error is not None
    assert outcome.error.code in {
        "workspace_mutated_after_verification",
        "independent_verification_failed",
        "artifact_hash_mismatch",
    }


def test_ac11_transaction_metadata_absent_from_promoted_tree(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-11 — promoted commit tree has no .governed-ephemeral.json."""
    from governed_ai.core.execution_gateway.transactional import tree_paths_at

    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit)
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.ok, outcome.error
    assert outcome.promoted_sha
    # Inspect the ephemeral worktree commit if still present; else project promotions.
    promo = json.loads(
        (workspace.ai_team / "supervisor" / "promotions" / "EXE-1.json").read_text(encoding="utf-8")
    )
    ephemeral = Path(promo["ephemeral_path"])
    if ephemeral.is_dir():
        tree = tree_paths_at(ephemeral, outcome.promoted_sha)
    else:
        tree = tree_paths_at(workspace.root, outcome.promoted_sha)
    assert ".governed-ephemeral.json" not in tree
    assert all(not path.startswith(".ai-team/supervisor/") for path in tree)
    assert all(path.startswith("src/") or path.startswith(".ai-team/evidence/") or path == "README.md" for path in tree)


def test_ac12_evidence_hash_matches_final_commit(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-12 — recorded artifact hash matches bytes at promoted SHA."""
    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit)
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.ok and outcome.result is not None
    artifacts = outcome.result["artifacts"]
    assert artifacts
    observed = artifacts[0]["observed_sha256"]
    promo = json.loads(
        (workspace.ai_team / "supervisor" / "promotions" / "EXE-1.json").read_text(encoding="utf-8")
    )
    ephemeral = Path(promo["ephemeral_path"])
    root = ephemeral if ephemeral.is_dir() else workspace.root
    blob = subprocess.run(
        ["git", "show", f"{outcome.promoted_sha}:{artifacts[0]['path']}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    import hashlib

    digest = f"sha256:{hashlib.sha256(blob).hexdigest()}"
    assert digest == observed


def test_ac13_hostile_combined_scenario(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-13 — hostile combo refused with no promotion/checkpoint."""
    workspace, sha = _workspace(tmp_path)
    # Authoritative lease at epoch 2 while request claims epoch 1.
    leases = workspace.ai_team / "runs" / "leases"
    leases.mkdir(parents=True, exist_ok=True)
    (workspace.ai_team / "runs").mkdir(parents=True, exist_ok=True)
    (workspace.ai_team / "runs" / "RUN-1.yaml").write_text(
        "id: RUN-1\nleases_by_work_unit:\n  WU-A:\n    lease_id: LEASE-2\n    epoch: 2\n",
        encoding="utf-8",
    )
    (leases / "LEASE-1.yaml").write_text(
        "id: LEASE-1\nstatus: superseded\nepoch: 1\n",
        encoding="utf-8",
    )
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    request, _ = _compile(gateway, sha, work_unit, grant_allowed_paths=["src/**"])

    class _Hostile:
        def execute(self, req: dict[str, Any]) -> dict[str, Any]:
            payload = FakeProductAdapter(hostile=True, bad_hash=True).execute(req)
            payload["workspace"]["claimed_result_sha"] = "c" * 40
            payload["checks"] = [
                {
                    "canonical_id": "tests",
                    "reported_name": "tests",
                    "status": "passed",
                    "blocking": True,
                    "trust_level": "agent_reported",
                }
            ]
            return payload

    outcome = gateway.execute(
        request=request,
        adapter=_Hostile(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**"],
        use_ephemeral_workspace=True,
        run_independent_verification=False,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert not list((workspace.ai_team / "supervisor" / "promotions").glob("*.json"))
    assert (workspace.ai_team / "supervisor" / "quarantine" / "EXE-1").is_dir()


def test_ac14_queue_journal_concurrency(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-14 — single lease winner; no duplicate journal sequences."""
    import threading

    from governed_ai.core.supervisor import journal, queue
    from governed_ai.core.supervisor.file_lock import SupervisorLockError

    workspace, _ = _workspace(tmp_path)
    ai_team = workspace.ai_team
    queue.enqueue(ai_team, run_id="RUN-1", kind="tick", max_attempts=5)
    winners: list[str] = []
    errors: list[str] = []

    def _race() -> None:
        try:
            leased = queue.lease_next(ai_team, worker_id=f"w-{threading.get_ident()}")
            if leased is not None:
                winners.append(str(leased["lease_id"]))
        except (Exception, SupervisorLockError) as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=_race) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    # On Windows, transient lock contention may surface; still require ≤1 winner.
    assert len(winners) == 1, (winners, errors)

    sequences: list[int] = []
    journal_errors: list[str] = []

    def _append(i: int) -> None:
        try:
            document = journal.append_event(
                ai_team,
                instance_id="test",
                event_type="probe",
                payload={"i": i},
            )
            sequences.append(int(document["sequence"]))
        except Exception as exc:  # noqa: BLE001
            journal_errors.append(str(exc))

    threads = [threading.Thread(target=_append, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not journal_errors, journal_errors
    assert len(sequences) == 20
    assert len(set(sequences)) == 20
    assert sorted(sequences) == list(range(1, 21))

    item2 = queue.enqueue(ai_team, run_id="RUN-1", kind="tick2")
    leased2 = queue.lease_next(ai_team, worker_id="w2")
    assert leased2 is not None
    with pytest.raises(PermissionError):
        queue.complete(
            ai_team,
            str(item2["id"]),
            lease_id="QL-stale",
            lease_epoch=0,
        )


def test_ac15_toctou_out_of_scope_and_symlink(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-15 — post-verify out-of-scope / symlink creation refused."""
    import sys

    workspace, sha = _workspace(tmp_path)
    gateway = AgentExecutionGateway(workspace)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
    }
    script = tmp_path / "hack_state.py"
    script.write_text(
        "from pathlib import Path\n"
        "p = Path('.ai-team/state')\n"
        "p.mkdir(parents=True, exist_ok=True)\n"
        "(p / 'hacked.yaml').write_text('x: 1\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    hack = f"{sys.executable} {script}"
    request, _ = _compile(gateway, sha, work_unit, allowed_shell_commands=[hack])
    profile = {"commands": {"lint": hack}}
    outcome = gateway.execute(
        request=request,
        adapter=FakeProductAdapter(),
        work_unit=work_unit,
        grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
        profile=profile,
        use_ephemeral_workspace=True,
        run_independent_verification=True,
    )
    assert outcome.status == "rejected"
    assert outcome.promoted_sha is None
    assert outcome.error is not None
    assert outcome.error.code in {
        "workspace_mutated_after_verification",
        "scope_violation",
        "forbidden_control_plane_path",
    }


def test_ac16_supervisor_real_path_without_accept_execution(tmp_path: Path) -> None:
    """EXEC-GATEWAY-AC-16 — Supervisor → Gateway via run_governed_execution (not accept_execution)."""
    workspace, sha = _workspace(tmp_path)
    work_unit = {
        "id": "WU-A",
        "scope": {"include": ["src/**", ".ai-team/evidence/WU-A/**"], "exclude": []},
        "acceptance_criteria": [],
        "title": "Update app",
    }
    daemon = SupervisorDaemon(workspace, interval_seconds=0.05)
    daemon.acquire()
    try:
        outcome = daemon.run_governed_execution(
            adapter=FakeProductAdapter(),
            work_unit=work_unit,
            run_id="RUN-1",
            execution_id="EXE-REAL",
            lease_id="LEASE-1",
            epoch=1,
            role_id="backend-developer",
            procedure_id="implement-work-unit",
            base_sha=sha,
            grant_allowed_paths=["src/**", ".ai-team/evidence/WU-A/**"],
            allowed_shell_commands=[],
            required_checks=["implementation"],
            use_ephemeral_workspace=True,
            run_independent_verification=False,
            fence_authoritative_lease=False,
            known_roles={"backend-developer"},
            role_procedures={"backend-developer": {"implement-work-unit"}},
        )
    finally:
        daemon.shutdown()
    assert outcome.ok, outcome.error
    assert outcome.promoted_sha
    assert outcome.result is not None
    assert outcome.result["status"] == "succeeded"
    assert outcome.result["workspace"]["resumable"] is True
