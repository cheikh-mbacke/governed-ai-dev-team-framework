"""WU-P3-GW-WU — CreateWorkUnit, TransitionWorkUnit and state machine tests."""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from PIL import Image
from tests.core.workspace_helpers import (
    FABRIC_ROOT,
    PAYLOAD_AI_TEAM,
    write_installed_client_profile,
)

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.design_authority.capture_backend import CaptureObservation, FnCaptureBackend
from governed_ai.core.design_authority.conformance import run_visual_conformance
from governed_ai.core.design_authority.contract import compile_design_contract
from governed_ai.core.design_authority.reference_set import create_reference_set
from governed_ai.core.design_authority.registry import register_local_artifact
from governed_ai.core.domain.work_unit.state_machine import (
    iter_forbidden_transitions,
    iter_permitted_transitions,
)
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimal_work_unit_payload(work_unit_id: str, **overrides) -> dict:
    base = {
        "id": work_unit_id,
        "title": "Test work unit",
        "objective": {"result": "test"},
        "scope": {"include": [], "exclude": []},
        "expected_behavior": "test behavior",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {"unit_tests": True},
    }
    base.update(overrides)
    return base


@pytest.fixture()
def wu_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team)
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "work-units").mkdir(parents=True)
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    return Workspace.from_root(tmp_path)


def _actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-wu-test",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _create_envelope(work_unit_id: str, **payload_overrides) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-create-{work_unit_id}",
        "idempotency_key": f"idem-create-{work_unit_id}",
        "correlation_id": "COR-wu-create",
        "type": "CreateWorkUnit",
        "issued_at": "2026-08-29T17:30:00Z",
        "actor": _actor(),
        "target": {"kind": "work_unit", "id": work_unit_id},
        "payload": _minimal_work_unit_payload(work_unit_id, **payload_overrides),
    }


def _transition_envelope(
    work_unit_id: str,
    *,
    expected_revision: int,
    to_status: str,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-trans-{work_unit_id}-{to_status}",
        "idempotency_key": idempotency_key or f"idem-trans-{work_unit_id}-{to_status}",
        "correlation_id": "COR-wu-trans",
        "type": "TransitionWorkUnit",
        "issued_at": "2026-08-29T17:31:00Z",
        "actor": _actor(),
        "target": {
            "kind": "work_unit",
            "id": work_unit_id,
            "expected_revision": expected_revision,
        },
        "payload": {"to_status": to_status, "reason": "state machine test"},
    }


def _seed_work_unit(
    workspace: Workspace,
    work_unit_id: str,
    *,
    status: str = "ready",
    revision: int = 1,
    **document_overrides,
) -> None:
    document = _minimal_work_unit_payload(work_unit_id, status=status, **document_overrides)
    document["revision"] = revision
    document.setdefault("events", [])
    document.setdefault("evidence", [])
    document.setdefault(
        "outcomes",
        {
            "review_status": "pending",
            "audit_status": "not_required",
            "critical_open_items": [],
            "defects": [],
            "audit_findings": [],
            "human_acceptance": None,
        },
    )
    path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_create_work_unit_via_gateway(wu_workspace: Workspace) -> None:
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(_create_envelope("WU-CREATE-001"))
    assert exit_code == 0
    assert receipt["status"] == "accepted"
    created = yaml.safe_load(
        (wu_workspace.ai_team / "work-units" / "WU-CREATE-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert created["status"] == "draft"
    assert created["revision"] == 1


def test_create_work_unit_rejects_duplicate(wu_workspace: Workspace) -> None:
    gateway = CommandGateway(wu_workspace)
    gateway.execute_command(_create_envelope("WU-DUP-001"))
    duplicate = _create_envelope("WU-DUP-001")
    duplicate["idempotency_key"] = "idem-create-WU-DUP-001-retry"
    duplicate["command_id"] = "CMD-create-WU-DUP-001-retry"
    receipt, exit_code = gateway.execute_command(duplicate)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value


def test_cg003_stale_revision_on_transition(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-STALE-001", status="ready")
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope("WU-STALE-001", expected_revision=99, to_status="in_progress")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


@pytest.mark.parametrize("from_status,to_status", iter_permitted_transitions())
def test_permitted_transitions_accepted(
    wu_workspace: Workspace, from_status: str, to_status: str
) -> None:
    work_unit_id = f"WU-PERM-{from_status}-{to_status}".replace("_", "-")
    _seed_work_unit(wu_workspace, work_unit_id, status=from_status)
    if to_status == "done":
        path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["evidence"] = ["EV-test"]
        document["outcomes"]["review_status"] = "approved"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status=to_status)
    )
    assert exit_code == 0, receipt
    updated = yaml.safe_load(
        (wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert updated["status"] == to_status
    assert updated["revision"] == 2


@pytest.mark.parametrize("from_status,to_status", iter_forbidden_transitions())
def test_forbidden_transitions_rejected(
    wu_workspace: Workspace, from_status: str, to_status: str
) -> None:
    work_unit_id = f"WU-FORB-{from_status}-{to_status}".replace("_", "-")
    _seed_work_unit(wu_workspace, work_unit_id, status=from_status)
    before = (
        wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    ).read_text(encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status=to_status)
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_TRANSITION.value
    after = (wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").read_text(
        encoding="utf-8"
    )
    assert before == after


def test_done_transition_requires_prerequisites(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-DONE-GUARD", status="verification")
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope("WU-DONE-GUARD", expected_revision=1, to_status="done")
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def _png_bytes(color: tuple[int, int, int] = (30, 144, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _init_git(workspace: Workspace) -> str:
    root = workspace.root
    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "commit", "--allow-empty", "-m", "init"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _bind_visual_design(wu_workspace: Workspace, work_unit_id: str) -> tuple[str, bytes]:
    """Register an authoritative mockup, compile a Design Contract, and bind
    it to ``work_unit_id`` in conform mode. Returns (design_contract_id, ref_png)."""
    ref_png = _png_bytes()
    mockup = wu_workspace.root / "designs" / "screen.png"
    mockup.parent.mkdir(parents=True, exist_ok=True)
    mockup.write_bytes(ref_png)
    register_local_artifact(
        wu_workspace,
        design_artifact_id="DA-WU-DONE",
        relative_path="designs/screen.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
        screens=["home"],
        states=["content_available"],
    )
    create_reference_set(
        wu_workspace,
        design_reference_set_id="DRS-WU-DONE",
        title="Home set",
        created_by="human:designer",
        members=[
            {
                "design_artifact_id": "DA-WU-DONE",
                "target": {"route": "/", "state": "content_available"},
            }
        ],
    )
    compile_design_contract(
        wu_workspace,
        design_contract_id="DC-WU-DONE",
        design_mode="conform",
        design_reference_set_id="DRS-WU-DONE",
        compiled_by="human:designer",
        routes=["/"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 800, "height": 600}],
    )
    path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["design_binding"] = {
        "design_contract_id": "DC-WU-DONE",
        "design_reference_set_id": "DRS-WU-DONE",
        "design_mode": "conform",
        "states": ["content_available"],
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return "DC-WU-DONE", ref_png


def test_done_transition_blocked_without_visual_conformance_report(
    wu_workspace: Workspace,
) -> None:
    """Section 8/15 item 14 — a visually-bound Work Unit cannot reach Done on
    evidence + review approval alone; a passing, fresh VCR is required too."""
    work_unit_id = "WU-DONE-VISUAL-MISSING"
    _seed_work_unit(wu_workspace, work_unit_id, status="verification")
    _bind_visual_design(wu_workspace, work_unit_id)
    path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["evidence"] = ["EV-test"]
    document["outcomes"]["review_status"] = "approved"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status="done")
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_done_transition_blocked_by_forged_visual_conformance_report(
    wu_workspace: Workspace,
) -> None:
    """Section 8/15 item 14/16 — an agent cannot self-issue a fake 'passed'
    conformance report by writing the YAML directly; Done must recompute the
    report_hash and refuse a document that doesn't match its own content."""
    work_unit_id = "WU-DONE-VISUAL-FORGED"
    _seed_work_unit(wu_workspace, work_unit_id, status="verification")
    design_contract_id, _ref_png = _bind_visual_design(wu_workspace, work_unit_id)
    sha = _init_git(wu_workspace)

    forged_report = {
        "report_id": "VCR-FORGED",
        "schema_version": 1,
        "design_contract_id": design_contract_id,
        "design_contract_hash": "sha256:" + "0" * 64,
        "work_unit_id": work_unit_id,
        "commit_sha": sha,
        "status": "passed",
        "blocks_progress": False,
        "divergences": [],
        "captures": [],
        "implementer_role": "frontend-developer",
        "verifier_role": "frontend-developer",  # also same-actor — doubly forged
        "created_at": "2026-09-14T00:00:00Z",
        "report_hash": "sha256:" + "f" * 64,  # never recomputed by the Core
    }
    conformance_dir = wu_workspace.ai_team / "design" / "conformance"
    conformance_dir.mkdir(parents=True, exist_ok=True)
    (conformance_dir / "VCR-FORGED.yaml").write_text(
        yaml.safe_dump(forged_report), encoding="utf-8"
    )

    path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["evidence"] = ["EV-test"]
    document["outcomes"]["review_status"] = "approved"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status="done")
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_done_transition_allowed_with_genuine_passing_visual_conformance_report(
    wu_workspace: Workspace,
) -> None:
    """The positive counterpart: a real, Core-computed passing VCR for the
    exact delivered commit does let a visually-bound Work Unit reach Done."""
    work_unit_id = "WU-DONE-VISUAL-OK"
    _seed_work_unit(wu_workspace, work_unit_id, status="verification")
    _design_contract_id, ref_png = _bind_visual_design(wu_workspace, work_unit_id)
    sha = _init_git(wu_workspace)

    def _capture(_spec: dict) -> CaptureObservation:
        return CaptureObservation(screenshot_bytes=ref_png, dom={}, styles={}, environment={})

    run_visual_conformance(
        wu_workspace,
        report_id="VCR-WU-DONE-OK",
        design_contract_id="DC-WU-DONE",
        work_unit_id=work_unit_id,
        commit_sha=sha,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        capture_backend=FnCaptureBackend(_capture),
    )

    path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["evidence"] = ["EV-test"]
    document["outcomes"]["review_status"] = "approved"
    document["outcomes"]["delivered_commit_sha"] = sha
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status="done")
    )
    assert exit_code == 0, receipt
    updated = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert updated["status"] == "done"


def test_work_unit_done_query(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-QUERY-DONE", status="verification")
    gateway = CommandGateway(wu_workspace)
    result = gateway.query("work-unit-done", args={"work_unit_id": "WU-QUERY-DONE"})
    assert result["done"] is False
    assert "evidence" in result["missing"]
