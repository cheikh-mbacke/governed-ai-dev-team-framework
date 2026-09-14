"""Design Authority & Visual Conformance Pipeline tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from governed_ai.core.design_authority.binding import (
    DesignBindingError,
    bind_design_to_work_unit,
    evaluate_g1_design_readiness,
)
from governed_ai.core.design_authority.conformance import (
    ConformanceError,
    run_visual_conformance,
)
from governed_ai.core.design_authority.contract import compile_design_contract
from governed_ai.core.design_authority.context import build_multimodal_design_context
from governed_ai.core.design_authority.design_system import (
    detect_design_system_conflict,
    require_search_before_create,
    save_inventory,
)
from governed_ai.core.design_authority.hashing import sha256_bytes, sha256_file
from governed_ai.core.design_authority.procedure_select import (
    ProcedureSelectionError,
    select_frontend_procedure,
)
from governed_ai.core.design_authority.reconcile import reconcile_design_revision
from governed_ai.core.design_authority.reference_set import create_reference_set
from governed_ai.core.design_authority.registry import (
    DesignRegistryError,
    register_local_artifact,
    register_remote_artifact,
    verify_artifact_integrity,
)
from governed_ai.core.design_authority.security import DesignSecurityError, validate_local_artifact
from governed_ai.core.execution_gateway.capabilities import build_capability_descriptor
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError
from governed_ai.core.execution_gateway.gateway import AgentExecutionGateway
from governed_ai.core.workspace import Workspace

REPO = Path(__file__).resolve().parents[2]
PAYLOAD_SCHEMAS = REPO / "distribution" / "payload" / ".ai-team" / "schemas"
PAYLOAD_CONTRACTS = REPO / "distribution" / "payload" / ".ai-team" / "contracts"


def _workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "project"
    root.mkdir()
    ai = root / ".ai-team"
    ai.mkdir()
    (ai / "work-units").mkdir()
    (ai / "locks").mkdir()
    (ai / ".transactions").mkdir()
    shutil.copytree(PAYLOAD_SCHEMAS, ai / "schemas")
    shutil.copytree(PAYLOAD_CONTRACTS, ai / "contracts")
    (root / "designs").mkdir()
    return Workspace.from_root(root)


def _png(path: Path, payload: bytes = b"\x89PNG\r\n\x1a\n" + b"mock-design-v1") -> Path:
    path.write_bytes(payload)
    return path


def _write_wu(workspace: Workspace, wu_id: str = "WU-UI-1") -> dict[str, Any]:
    doc = {
        "id": wu_id,
        "title": "Login screen",
        "objective": {"result": "Implement login UI from mockup"},
        "scope": {"include": ["frontend/**"], "exclude": []},
        "expected_behavior": "Matches authoritative mockup",
        "acceptance_criteria": ["visual conformance passed"],
        "dependencies": [],
        "risk": {"class": "medium"},
        "required_verification": {"qa": True, "accessibility_check": True},
        "status": "ready",
        "revision": 1,
        "created_at": "2026-09-14T00:00:00Z",
        "updated_at": "2026-09-14T00:00:00Z",
        "zone": {"area": "frontend"},
    }
    import yaml

    path = workspace.ai_team / "work-units" / f"{wu_id}.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return doc


def test_register_png_with_core_hash(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    rel = "designs/login.png"
    _png(ws.root / rel)
    doc = register_local_artifact(
        ws,
        design_artifact_id="DA-LOGIN-1",
        relative_path=rel,
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer", "authorization_id": "HAUTH-1"},
        screens=["login"],
        states=["content_available"],
    )
    assert doc["content_hash"].startswith("sha256:")
    assert doc["content_hash"] == sha256_file(ws.root / rel)
    assert doc["authority_level"] == "authoritative"


def test_register_svg_pdf_and_remote(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    svg = ws.root / "designs" / "icon.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>')
    pdf = ws.root / "designs" / "spec.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    svg_doc = register_local_artifact(
        ws,
        design_artifact_id="DA-SVG-1",
        relative_path="designs/icon.svg",
        registered_by="human:designer",
        authority_level="advisory",
        source_type="svg",
    )
    pdf_doc = register_local_artifact(
        ws,
        design_artifact_id="DA-PDF-1",
        relative_path="designs/spec.pdf",
        registered_by="human:designer",
        authority_level="advisory",
        source_type="pdf",
    )
    pin = sha256_bytes(b"figma-node-frozen")
    remote = register_remote_artifact(
        ws,
        design_artifact_id="DA-FIGMA-1",
        source_uri="https://www.figma.com/file/abc/Login",
        registered_by="human:designer",
        authority_level="authoritative",
        content_pin=pin,
        human_authorization={"granted_by": "human:designer"},
    )
    assert svg_doc["source_type"] == "svg"
    assert pdf_doc["source_type"] == "pdf"
    assert remote["frozen_remote"]["content_pin"] == pin


def test_agent_cannot_self_authorize_authoritative(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "x.png")
    with pytest.raises(DesignRegistryError) as exc:
        register_local_artifact(
            ws,
            design_artifact_id="DA-X",
            relative_path="designs/x.png",
            registered_by="agent:frontend-developer",
            authority_level="authoritative",
            human_authorization={
                "granted_by": "agent:frontend-developer",
                "authorization_id": "HAUTH-BAD",
            },
        )
    assert exc.value.code == "agent_cannot_self_authorize"


def test_modified_reference_detected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    path = ws.root / "designs" / "a.png"
    _png(path, b"\x89PNG\r\n\x1a\n" + b"v1")
    doc = register_local_artifact(
        ws,
        design_artifact_id="DA-A",
        relative_path="designs/a.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"v2-changed")
    integrity = verify_artifact_integrity(ws, doc)
    assert integrity["ok"] is False
    assert integrity["code"] == "reference_modified_after_approval"


def test_contradictory_authoritative_references_block(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "a.png", b"\x89PNG\r\n\x1a\n" + b"a")
    _png(ws.root / "designs" / "b.png", b"\x89PNG\r\n\x1a\n" + b"b")
    for aid, rel in (("DA-1", "designs/a.png"), ("DA-2", "designs/b.png")):
        register_local_artifact(
            ws,
            design_artifact_id=aid,
            relative_path=rel,
            registered_by="human:designer",
            authority_level="authoritative",
            human_authorization={"granted_by": "human:designer"},
        )
    with pytest.raises(Exception) as exc:
        create_reference_set(
            ws,
            design_reference_set_id="DRS-1",
            title="Login",
            created_by="human:designer",
            members=[
                {
                    "design_artifact_id": "DA-1",
                    "target": {"route": "/login", "state": "content_available", "viewport": "desktop"},
                },
                {
                    "design_artifact_id": "DA-2",
                    "target": {"route": "/login", "state": "content_available", "viewport": "desktop"},
                },
            ],
        )
    assert "contradictory" in str(exc.value).lower() or "blocking" in str(exc.value).lower()


def test_advisory_does_not_auto_block_conformance(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "adv.png")
    register_local_artifact(
        ws,
        design_artifact_id="DA-ADV",
        relative_path="designs/adv.png",
        registered_by="human:designer",
        authority_level="advisory",
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-ADV",
        title="Advisory",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-ADV", "target": {"route": "/x"}}],
    )
    # create mode with advisory refs is fine; compile create without auth refs
    contract = compile_design_contract(
        ws,
        design_contract_id="DC-ADV",
        design_mode="create",
        design_reference_set_id="DRS-ADV",
        compiled_by="human:designer",
        routes=["/x"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 1280, "height": 800}],
        mandatory_text=["Hello"],
    )
    report = run_visual_conformance(
        ws,
        report_id="VCR-ADV",
        design_contract_id="DC-ADV",
        work_unit_id="WU-UI-1",
        commit_sha="a" * 40,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        observations=[
            {
                "route": "/x",
                "state": "content_available",
                "viewport": {"name": "desktop"},
                "observed_text": [],
                "observed_components": [],
            }
        ],
    )
    assert report["status"] in {"passed", "failed"}
    # advisory must not produce blocks_progress solely from advisory authority
    if report["divergences"]:
        assert all(
            not d.get("blocks_progress")
            for d in report["divergences"]
            if d.get("authority_level") == "advisory"
        )


def test_procedure_conform_vs_create() -> None:
    assert select_frontend_procedure(design_mode="conform") == "implement-approved-design"
    assert select_frontend_procedure(design_mode="create") == "create-frontend-design"
    with pytest.raises(ProcedureSelectionError):
        select_frontend_procedure(design_mode="conform", requested_procedure="frontend-design")


def test_design_system_search_and_conflict(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    inventory = {
        "schema_version": 1,
        "revision": 1,
        "components": [{"name": "Button", "path": "src/ui/Button.tsx"}],
        "deprecated_components": [{"name": "LegacyButton"}],
        "tokens": {"color.primary": "#111111"},
        "usage_rules": ["prefer Button over raw <button>"],
    }
    save_inventory(ws, inventory)
    search = require_search_before_create(inventory, proposed_name="Button")
    assert search["may_create"] is False
    conflict = detect_design_system_conflict(
        inventory=inventory,
        mockup_requirements={
            "components": ["LegacyButton"],
            "tokens": {"color.primary": "#FF0000"},
        },
        precedence="escalate_on_conflict",
    )
    assert conflict["has_conflict"] is True
    assert conflict["decision_required"] is True


def test_security_svg_and_path_traversal(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    bad = ws.root / "designs" / "evil.svg"
    bad.write_text('<svg><script>alert(1)</script></svg>')
    with pytest.raises(DesignSecurityError) as exc:
        validate_local_artifact(ws.root, "designs/evil.svg", source_type="svg")
    assert exc.value.code == "unsafe_svg_content"

    with pytest.raises(DesignSecurityError) as exc2:
        validate_local_artifact(ws.root, "../outside.png")
    assert exc2.value.code == "forbidden_path_traversal"


def test_backend_project_without_design(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    doc = {
        "id": "WU-BE-1",
        "zone": {"area": "backend"},
        "design_binding": {},
    }
    readiness = evaluate_g1_design_readiness(ws, doc)
    assert readiness["ok"] is True
    assert readiness["applicable"] is False
    assert build_multimodal_design_context(ws, work_unit=doc) is None


def test_same_actor_cannot_verify(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "c.png")
    register_local_artifact(
        ws,
        design_artifact_id="DA-C",
        relative_path="designs/c.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-C",
        title="C",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-C", "target": {"route": "/"}}],
    )
    compile_design_contract(
        ws,
        design_contract_id="DC-C",
        design_mode="conform",
        design_reference_set_id="DRS-C",
        compiled_by="human:designer",
        routes=["/"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 1280, "height": 800}],
    )
    with pytest.raises(ConformanceError) as exc:
        run_visual_conformance(
            ws,
            report_id="VCR-SAME",
            design_contract_id="DC-C",
            work_unit_id="WU-UI-1",
            commit_sha="b" * 40,
            verifier_role="frontend-developer",
            implementer_role="frontend-developer",
            observations=[],
        )
    assert exc.value.code == "same_actor_implementation_and_verification"


def test_stale_lease_epoch_refused(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "d.png")
    register_local_artifact(
        ws,
        design_artifact_id="DA-D",
        relative_path="designs/d.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-D",
        title="D",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-D", "target": {"route": "/"}}],
    )
    compile_design_contract(
        ws,
        design_contract_id="DC-D",
        design_mode="conform",
        design_reference_set_id="DRS-D",
        compiled_by="human:designer",
        routes=["/"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 1280, "height": 800}],
    )
    with pytest.raises(ConformanceError) as exc:
        run_visual_conformance(
            ws,
            report_id="VCR-STALE",
            design_contract_id="DC-D",
            work_unit_id="WU-UI-1",
            commit_sha="c" * 40,
            verifier_role="visual-qa",
            implementer_role="frontend-developer",
            lease_id="LEASE-OLD",
            epoch=1,
            expected_lease_id="LEASE-NEW",
            expected_epoch=2,
            observations=[],
        )
    assert exc.value.code == "stale_lease"


def test_end_to_end_conformant_pipeline(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _write_wu(ws)
    mock = _png(ws.root / "designs" / "login.png", b"\x89PNG\r\n\x1a\n" + b"login-ref")
    art = register_local_artifact(
        ws,
        design_artifact_id="DA-LOGIN",
        relative_path="designs/login.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
        screens=["login"],
        states=["loading", "empty", "error", "access_denied", "content_available"],
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-LOGIN",
        title="Login set",
        created_by="human:designer",
        members=[
            {
                "design_artifact_id": "DA-LOGIN",
                "target": {
                    "route": "/login",
                    "state": "content_available",
                    "viewport": "desktop",
                },
            }
        ],
    )
    states = ["loading", "empty", "error", "access_denied", "content_available"]
    viewports = [
        {"name": "desktop", "width": 1280, "height": 800},
        {"name": "mobile", "width": 390, "height": 844},
    ]
    contract = compile_design_contract(
        ws,
        design_contract_id="DC-LOGIN",
        design_mode="conform",
        design_reference_set_id="DRS-LOGIN",
        compiled_by="human:designer",
        routes=["/login"],
        screens=["login"],
        mandatory_text=["Sign in"],
        mandatory_elements=["LoginForm"],
        states=states,
        viewports=viewports,
        tolerances={"difference_threshold": 0.05, "masked_regions": ["#clock"]},
    )
    binding = bind_design_to_work_unit(
        ws,
        work_unit_id="WU-UI-1",
        design_contract_id="DC-LOGIN",
        design_mode="conform",
    )
    assert binding["design_mode"] == "conform"

    import yaml

    wu = yaml.safe_load((ws.ai_team / "work-units" / "WU-UI-1.yaml").read_text(encoding="utf-8"))
    g1 = evaluate_g1_design_readiness(ws, wu)
    assert g1["ok"] is True

    ctx = build_multimodal_design_context(ws, work_unit=wu)
    assert ctx is not None
    assert ctx["design_contract_id"] == "DC-LOGIN"
    assert ctx["design_context_hash"].startswith("sha256:")
    assert any(r["verified_accessible"] for r in ctx["references"])

    # Fake visual adapter capabilities required for dispatch.
    caps = build_capability_descriptor(
        adapter_id="fake-visual",
        adapter_version="1.0.0",
        supported_protocol_versions=["1.0"],
        supported_roles=["frontend-developer"],
        supported_procedures=["implement-approved-design"],
        isolated_workspace=True,
        cancellation=True,
        progress_events=True,
        structured_output=True,
        command_enforcement=True,
        filesystem_enforcement=True,
        visual_input=True,
        screenshot=True,
        visual_formats=["png"],
    )
    gateway = AgentExecutionGateway(workspace=ws)
    request, compiled = gateway.compile_request(
        execution_id="EXE-UI-1",
        run_id="RUN-1",
        work_unit=wu,
        lease_id="LEASE-1",
        epoch=1,
        role_id="frontend-developer",
        procedure_id="implement-approved-design",
        base_sha="d" * 40,
        grant_allowed_paths=["frontend/**"],
        allowed_shell_commands=[],
        required_checks=["implementation"],
        capabilities=caps,
        known_roles={"frontend-developer"},
        role_procedures={"frontend-developer": {"implement-approved-design"}},
    )
    assert "design" in compiled
    assert compiled["design"]["design_mode"] == "conform"
    assert request["context_package_hash"] == compiled["context_package_hash"]

    # Missing visual capability refused.
    caps_blind = dict(caps)
    caps_blind["visual_input"] = False
    with pytest.raises(ExecutionGatewayError) as exc:
        gateway.compile_request(
            execution_id="EXE-UI-2",
            run_id="RUN-1",
            work_unit=wu,
            lease_id="LEASE-1",
            epoch=1,
            role_id="frontend-developer",
            procedure_id="implement-approved-design",
            base_sha="d" * 40,
            grant_allowed_paths=["frontend/**"],
            allowed_shell_commands=[],
            required_checks=["implementation"],
            capabilities=caps_blind,
            known_roles={"frontend-developer"},
            role_procedures={"frontend-developer": {"implement-approved-design"}},
        )
    assert exc.value.code == "missing_visual_input_capability"

    ref_bytes = mock.read_bytes()
    observations = []
    for vp in viewports:
        for state in states:
            observations.append(
                {
                    "route": "/login",
                    "state": state,
                    "viewport": vp,
                    "observed_text": ["Sign in"],
                    "observed_components": ["LoginForm"],
                    "screenshot_bytes": ref_bytes,
                    "reference_screenshot_bytes": ref_bytes,
                    "diff_ratio": 0.0,
                }
            )
    report = run_visual_conformance(
        ws,
        report_id="VCR-LOGIN-OK",
        design_contract_id="DC-LOGIN",
        work_unit_id="WU-UI-1",
        commit_sha="e" * 40,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        observations=observations,
    )
    assert report["status"] == "passed"
    assert report["blocks_progress"] is False
    for capture in report["captures"]:
        assert capture["route"] == "/login"
        assert capture["commit_sha"] == "e" * 40
        assert capture["reference_id"] == "DA-LOGIN"
        assert capture["viewport"] is not None

    # Hostile agent: ignores mockup, changes palette signal, removes mandatory component.
    hostile = run_visual_conformance(
        ws,
        report_id="VCR-LOGIN-HOSTILE",
        design_contract_id="DC-LOGIN",
        work_unit_id="WU-UI-1",
        commit_sha="f" * 40,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        observations=[
            {
                "route": "/login",
                "state": "content_available",
                "viewport": {"name": "desktop"},
                "observed_text": ["Welcome elsewhere"],
                "observed_components": [],  # removed LoginForm
                "screenshot_bytes": b"\x89PNG\r\n\x1a\n" + b"totally-different",
                "reference_screenshot_bytes": ref_bytes,
                "diff_ratio": 0.9,
            }
        ],
        agent_claimed_passed=True,
    )
    assert hostile["status"] == "failed"
    assert hostile["blocks_progress"] is True
    assert art["content_hash"] == sha256_file(mock)


def test_design_revision_invalidates_only_related(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _write_wu(ws, "WU-A")
    _write_wu(ws, "WU-B")
    _png(ws.root / "designs" / "old.png", b"\x89PNG\r\n\x1a\n" + b"old")
    _png(ws.root / "designs" / "new.png", b"\x89PNG\r\n\x1a\n" + b"new")
    register_local_artifact(
        ws,
        design_artifact_id="DA-OLD",
        relative_path="designs/old.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    register_local_artifact(
        ws,
        design_artifact_id="DA-NEW",
        relative_path="designs/new.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
        supersedes="DA-OLD",
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-OLD",
        title="old",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-OLD", "target": {"route": "/a"}}],
    )
    compile_design_contract(
        ws,
        design_contract_id="DC-OLD",
        design_mode="conform",
        design_reference_set_id="DRS-OLD",
        compiled_by="human:designer",
        routes=["/a"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 1280, "height": 800}],
    )
    bind_design_to_work_unit(
        ws, work_unit_id="WU-A", design_contract_id="DC-OLD", design_mode="conform"
    )
    run_visual_conformance(
        ws,
        report_id="VCR-OLD",
        design_contract_id="DC-OLD",
        work_unit_id="WU-A",
        commit_sha="1" * 40,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        observations=[
            {
                "route": "/a",
                "state": "content_available",
                "viewport": {"name": "desktop"},
                "observed_text": [],
                "observed_components": [],
            }
        ],
    )
    impact = reconcile_design_revision(
        ws,
        reconciliation_id="DR-1",
        previous_artifact_id="DA-OLD",
        new_artifact_id="DA-NEW",
        triggered_by="human:designer",
    )
    assert "WU-A" in impact["affected_work_units"]
    assert "WU-B" not in impact["affected_work_units"]
    assert "VCR-OLD" in impact["invalidated_conformance_reports"]


def test_create_blocked_when_authoritative_exists(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _write_wu(ws)
    _png(ws.root / "designs" / "z.png")
    register_local_artifact(
        ws,
        design_artifact_id="DA-Z",
        relative_path="designs/z.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-Z",
        title="Z",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-Z", "target": {"route": "/"}}],
    )
    with pytest.raises(Exception):
        compile_design_contract(
            ws,
            design_contract_id="DC-Z-CREATE",
            design_mode="create",
            design_reference_set_id="DRS-Z",
            compiled_by="human:designer",
        )
    with pytest.raises(DesignBindingError):
        bind_design_to_work_unit(
            ws,
            work_unit_id="WU-UI-1",
            design_reference_set_id="DRS-Z",
            design_mode="create",
        )


def test_allowed_adaptation_requires_tolerance_rule(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _png(ws.root / "designs" / "t.png", b"\x89PNG\r\n\x1a\n" + b"tol")
    register_local_artifact(
        ws,
        design_artifact_id="DA-T",
        relative_path="designs/t.png",
        registered_by="human:designer",
        authority_level="authoritative",
        human_authorization={"granted_by": "human:designer"},
    )
    create_reference_set(
        ws,
        design_reference_set_id="DRS-T",
        title="T",
        created_by="human:designer",
        members=[{"design_artifact_id": "DA-T", "target": {"route": "/"}}],
    )
    compile_design_contract(
        ws,
        design_contract_id="DC-T",
        design_mode="adapt",
        design_reference_set_id="DRS-T",
        compiled_by="human:designer",
        routes=["/"],
        states=["content_available"],
        viewports=[{"name": "desktop", "width": 1280, "height": 800}],
        tolerances={"difference_threshold": 0.1},
        free_zones=[{"id": "spacing", "description": "minor spacing"}],
    )
    ref = (ws.root / "designs" / "t.png").read_bytes()
    report = run_visual_conformance(
        ws,
        report_id="VCR-T",
        design_contract_id="DC-T",
        work_unit_id="WU-UI-1",
        commit_sha="2" * 40,
        verifier_role="visual-qa",
        implementer_role="frontend-developer",
        observations=[
            {
                "route": "/",
                "state": "content_available",
                "viewport": {"name": "desktop"},
                "observed_text": [],
                "observed_components": [],
                "screenshot_bytes": ref + b"x",
                "reference_screenshot_bytes": ref,
                "diff_ratio": 0.25,
                "allowed_by_tolerance_rule": "tolerances.difference_threshold",
            }
        ],
    )
    assert any(d["kind"] == "allowed_adaptation" for d in report["divergences"])
    assert report["blocks_progress"] is False
