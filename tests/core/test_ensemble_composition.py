"""Phase 6: composition-backed G3/G4, e2e evidence, and frozen member checkouts."""

from __future__ import annotations

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

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.design_authority.conformance import ConformanceError, run_visual_conformance
from governed_ai.core.ensemble_composition import (
    ensure_frozen_composition_checkouts,
    load_composition,
)
from governed_ai.core.orchestrator.git_workspace import head_sha
from governed_ai.core.persistence.lock import force_release_stale_lock
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def instance_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="acme-ai-team")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    (ai_team / "work-units").mkdir(parents=True)
    (ai_team / "evidence").mkdir(parents=True)
    (ai_team / "release-candidates").mkdir(parents=True)
    (ai_team / "authorizations").mkdir(parents=True)
    (ai_team / "decisions").mkdir(parents=True)
    return Workspace.from_root(tmp_path)


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


def _repository(root: Path, filename: str, content: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "member@example.test")
    _git(root, "config", "user.name", "Member")
    (root / filename).write_text(content, encoding="utf-8")
    _git(root, "add", filename)
    _git(root, "commit", "-m", "test: base")
    return root


def _actor(role_id: str = "control-plane") -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-p6",
        "role_id": role_id,
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _execute(workspace: Workspace, envelope: dict) -> tuple[dict, int]:
    force_release_stale_lock(workspace.ai_team / "locks" / "project.lock")
    return CommandGateway(workspace).execute_command(envelope)


def _register_pinned_ensemble(workspace: Workspace, tmp_path: Path) -> tuple[Path, Path, str]:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    for envelope in (
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ens-p6",
            "idempotency_key": "idem-ens-p6",
            "correlation_id": "COR-p6",
            "type": "RegisterEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"id": "boutique"},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-mem-be",
            "idempotency_key": "idem-mem-be",
            "correlation_id": "COR-p6",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            "payload": {"id": "backend", "kind": "service", "path": str(backend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-mem-fe",
            "idempotency_key": "idem-mem-fe",
            "correlation_id": "COR-p6",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 2},
            "payload": {"id": "frontend", "kind": "ui", "path": str(frontend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-act-p6",
            "idempotency_key": "idem-act-p6",
            "correlation_id": "COR-p6",
            "type": "SetActiveEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"ensemble_id": "boutique"},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-pin-p6",
            "idempotency_key": "idem-pin-p6",
            "correlation_id": "COR-p6",
            "type": "PinComposition",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "composition", "id": "CR-boutique-1"},
            "payload": {"id": "CR-boutique-1", "ensemble_id": "boutique"},
        },
    ):
        receipt, code = _execute(workspace, envelope)
        assert code == 0, receipt
    return backend, frontend, "CR-boutique-1"


def _gate_envelope(workspace: Workspace, *, gate: str, status: str, auth_id: str) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-{auth_id}",
        "idempotency_key": f"idem-{auth_id}",
        "correlation_id": "COR-p6",
        "type": "RecordGateDecision",
        "issued_at": "2026-09-18T12:00:00Z",
        "actor": _actor(),
        "target": {"kind": "gate_decision", "id": "new"},
        "payload": {"gate": gate, "status": status, "by": "test-human", "note": "p6"},
        "human_authorization": {
            "authorization_id": auth_id,
            "granted_by": "test-human",
            "granted_at": "2026-09-18T12:00:00Z",
            "scope": f"gate:{gate}",
            "consumed_at": None,
        },
    }


def test_g3_without_composition_is_rejected(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    for envelope in (
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ens-g3",
            "idempotency_key": "idem-ens-g3",
            "correlation_id": "COR-p6",
            "type": "RegisterEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"id": "boutique"},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-be-g3",
            "idempotency_key": "idem-be-g3",
            "correlation_id": "COR-p6",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            "payload": {"id": "backend", "kind": "service", "path": str(backend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-fe-g3",
            "idempotency_key": "idem-fe-g3",
            "correlation_id": "COR-p6",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 2},
            "payload": {"id": "frontend", "kind": "ui", "path": str(frontend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-act-g3",
            "idempotency_key": "idem-act-g3",
            "correlation_id": "COR-p6",
            "type": "SetActiveEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"ensemble_id": "boutique"},
        },
    ):
        receipt, code = _execute(instance_workspace, envelope)
        assert code == 0, receipt
    workspace = Workspace.from_root(instance_workspace.root)
    receipt, code = _execute(workspace, _gate_envelope(workspace, gate="G3", status="approved", auth_id="HAUTH-g3-miss"))
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert "composition_id" in receipt["errors"][0]["message"]


def test_g3_with_current_composition_is_accepted(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    receipt, code = _execute(workspace, _gate_envelope(workspace, gate="G3", status="approved", auth_id="HAUTH-g3-ok"))
    assert code == 0, receipt
    assert receipt["details"]["composition_id"] == "CR-boutique-1"


def test_standalone_g3_does_not_require_composition(instance_workspace: Workspace) -> None:
    receipt, code = _execute(
        instance_workspace,
        _gate_envelope(instance_workspace, gate="G3", status="approved", auth_id="HAUTH-g3-solo"),
    )
    assert code == 0, receipt
    assert "composition_id" not in (receipt.get("details") or {})


def test_release_candidate_requires_current_composition(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    members_path = workspace.ensemble_members_path
    document = yaml.safe_load(members_path.read_text(encoding="utf-8"))
    document.pop("current_composition", None)
    members_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-rc-miss",
            "idempotency_key": "idem-rc-miss",
            "correlation_id": "COR-p6",
            "type": "RegisterReleaseCandidate",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor("release-agent"),
            "target": {"kind": "release_candidate", "id": "RC-MISS"},
            "payload": {
                "id": "RC-MISS",
                "status": "draft",
                "code_revisions": ["abc123"],
                "included_work_units": [],
                "rollback_plan": "revert",
                "target_environment": "staging",
                "g3": {"status": "pending"},
            },
        },
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_release_candidate_stamps_current_composition(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-rc-ok",
            "idempotency_key": "idem-rc-ok",
            "correlation_id": "COR-p6",
            "type": "RegisterReleaseCandidate",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor("release-agent"),
            "target": {"kind": "release_candidate", "id": "RC-OK"},
            "payload": {
                "id": "RC-OK",
                "status": "draft",
                "code_revisions": ["abc123"],
                "included_work_units": [],
                "rollback_plan": "revert",
                "target_environment": "staging",
                "g3": {"status": "pending"},
            },
        },
    )
    assert code == 0, receipt
    recorded = yaml.safe_load(
        (workspace.ai_team / "release-candidates" / "RC-OK.yaml").read_text(encoding="utf-8")
    )
    assert recorded["composition_id"] == "CR-boutique-1"


def test_e2e_evidence_requires_live_composition(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _backend, frontend, composition_id = _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    composition = load_composition(workspace, composition_id)
    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ev-sha",
            "idempotency_key": "idem-ev-sha",
            "correlation_id": "COR-p6",
            "type": "RegisterEvidence",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor("qa-test"),
            "target": {"kind": "evidence", "id": "EV-SHA"},
            "payload": {
                "id": "EV-SHA",
                "type": "e2e",
                "code_revision": "a" * 40,
                "command_or_observation": "npm run e2e",
                "result": {"status": "passed"},
                "demonstrates": ["journey"],
                "limitations": [],
            },
        },
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value

    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ev-ok",
            "idempotency_key": "idem-ev-ok",
            "correlation_id": "COR-p6",
            "type": "RegisterEvidence",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor("qa-test"),
            "target": {"kind": "evidence", "id": "EV-OK"},
            "payload": {
                "id": "EV-OK",
                "type": "e2e",
                "code_revision": {
                    "kind": "composition",
                    "composition_id": composition_id,
                    "members": composition["members"],
                },
                "command_or_observation": "npm run e2e",
                "result": {"status": "passed"},
                "demonstrates": ["journey"],
                "limitations": [],
            },
        },
    )
    assert code == 0, receipt

    (frontend / "page.js").write_text("export default { next: true }\n", encoding="utf-8")
    _git(frontend, "add", "page.js")
    _git(frontend, "commit", "-m", "test: advance frontend")
    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ev-stale",
            "idempotency_key": "idem-ev-stale",
            "correlation_id": "COR-p6",
            "type": "RegisterEvidence",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor("qa-test"),
            "target": {"kind": "evidence", "id": "EV-STALE"},
            "payload": {
                "id": "EV-STALE",
                "type": "e2e",
                "code_revision": {
                    "kind": "composition",
                    "composition_id": composition_id,
                    "members": composition["members"],
                },
                "command_or_observation": "npm run e2e",
                "result": {"status": "passed"},
                "demonstrates": ["journey"],
                "limitations": [],
            },
        },
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert "frontend" in receipt["errors"][0]["message"]


def test_g4_rejects_diverged_member_head(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _backend, frontend, _composition_id = _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    (frontend / "page.js").write_text("export default { next: true }\n", encoding="utf-8")
    _git(frontend, "add", "page.js")
    _git(frontend, "commit", "-m", "test: advance frontend")
    receipt, code = _execute(
        workspace, _gate_envelope(workspace, gate="G4", status="accepted", auth_id="HAUTH-g4-stale")
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert "frontend" in receipt["errors"][0]["message"]


def test_frozen_checkouts_stay_at_pin_when_member_advances(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _backend, frontend, composition_id = _register_pinned_ensemble(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    composition = load_composition(workspace, composition_id)
    pinned = composition["members"]["frontend"]
    roots = ensure_frozen_composition_checkouts(workspace, composition)
    assert set(roots) == {"backend", "frontend"}
    assert head_sha(roots["frontend"]) == pinned
    (frontend / "page.js").write_text("export default { next: true }\n", encoding="utf-8")
    _git(frontend, "add", "page.js")
    _git(frontend, "commit", "-m", "test: advance frontend")
    assert head_sha(frontend) != pinned
    assert head_sha(roots["frontend"]) == pinned
    with pytest.raises(ConformanceError) as exc:
        run_visual_conformance(
            workspace,
            report_id="VCR-stale",
            design_contract_id="DC-missing",
            work_unit_id="WU-FRONT",
            commit_sha=head_sha(frontend),
            verifier_role="visual-qa",
            persist=False,
        )
    assert exc.value.code in {"composition_not_current", "commit_sha_composition_mismatch"}
