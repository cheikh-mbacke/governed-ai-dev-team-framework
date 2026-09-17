"""Phase 3 Command Gateway: RegisterEnsemble, RegisterMember, PinComposition."""

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

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.orchestrator.git_workspace import head_sha
from governed_ai.core.persistence.lock import force_release_stale_lock
from governed_ai.core.workspace import Workspace

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.fixture()
def instance_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="acme-ai-team")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: not_compiled\n", encoding="utf-8")
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
        "execution_id": "EXE-ensemble",
        "role_id": role_id,
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _envelope(command_type: str, *, target: dict, payload: dict, command_id: str, role_id: str = "control-plane") -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": command_id,
        "idempotency_key": f"idem-{command_id}",
        "correlation_id": f"COR-{command_id}",
        "type": command_type,
        "issued_at": "2026-09-17T12:00:00Z",
        "actor": _actor(role_id),
        "target": target,
        "payload": payload,
    }


def _execute(workspace: Workspace, envelope: dict) -> tuple[dict, int]:
    force_release_stale_lock(workspace.ai_team / "locks" / "project.lock")
    return CommandGateway(workspace).execute_command(envelope)


def _register_ensemble(workspace: Workspace, ensemble_id: str, command_id: str) -> dict:
    receipt, code = _execute(
        workspace,
        _envelope(
            "RegisterEnsemble",
            target={"kind": "ensemble", "id": ensemble_id},
            payload={"id": ensemble_id, "name": ensemble_id},
            command_id=command_id,
        ),
    )
    assert code == 0, receipt
    return receipt


def _members_revision(workspace: Workspace, ensemble_id: str) -> int:
    document = yaml.safe_load(
        (workspace.ensembles_root / ensemble_id / "members.yaml").read_text(encoding="utf-8")
    )
    return int(document["revision"])


def test_register_ensemble_and_two_members_updates_catalog(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-001")

    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            payload={"id": "backend", "kind": "service", "path": str(backend)},
            command_id="CMD-mem-001",
        ),
    )
    assert code == 0, receipt
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 2},
            payload={"id": "frontend", "kind": "ui", "path": str(frontend)},
            command_id="CMD-mem-002",
        ),
    )
    assert code == 0, receipt

    members = yaml.safe_load(
        (instance_workspace.ensembles_root / "boutique" / "members.yaml").read_text(encoding="utf-8")
    )
    assert [entry["id"] for entry in members["members"]] == ["backend", "frontend"]
    catalog = yaml.safe_load(instance_workspace.catalog_path.read_text(encoding="utf-8"))
    assert catalog["instance_id"] == "acme-ai-team"
    assert catalog["ensembles"] == [
        {"id": "boutique", "status": "registered", "members": ["backend", "frontend"]}
    ]
    backend_link = json.loads((backend / ".ai-team" / "member-link.json").read_text(encoding="utf-8"))
    assert backend_link["member_id"] == "backend"
    assert backend_link["ensemble_id"] == "boutique"
    assert backend_link["instance_path"] == str(instance_workspace.root)
    agents = (backend / "AGENTS.md").read_text(encoding="utf-8")
    assert "governed-ai-member:start" in agents
    assert str(instance_workspace.root) in agents


def test_non_git_and_instance_path_are_rejected(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-010")
    plain = tmp_path / "not-git"
    plain.mkdir()

    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            payload={"id": "backend", "kind": "service", "path": str(plain)},
            command_id="CMD-mem-ng",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value

    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            payload={"id": "hub", "kind": "other", "path": str(tmp_path)},
            command_id="CMD-mem-inst",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_register_member_revision_conflict(instance_workspace: Workspace, tmp_path: Path) -> None:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-020")
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 99},
            payload={"id": "backend", "kind": "service", "path": str(backend)},
            command_id="CMD-mem-conflict",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value
    assert _members_revision(instance_workspace, "boutique") == 1


def test_two_ensembles_keep_independent_project_state(instance_workspace: Workspace) -> None:
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-b")
    _register_ensemble(instance_workspace, "intranet", "CMD-ens-i")
    boutique_state = instance_workspace.ensembles_root / "boutique" / "state" / "project-state.yaml"
    intranet_state = instance_workspace.ensembles_root / "intranet" / "state" / "project-state.yaml"
    boutique = yaml.safe_load(boutique_state.read_text(encoding="utf-8"))
    boutique["phase"] = "awaiting_g1_approval"
    boutique["gates"] = {"G1": {"status": "awaiting_approval"}}
    boutique_state.write_text(yaml.safe_dump(boutique, sort_keys=False), encoding="utf-8")
    intranet = yaml.safe_load(intranet_state.read_text(encoding="utf-8"))
    assert intranet["phase"] == "not_compiled"
    assert boutique_state.read_text(encoding="utf-8") != intranet_state.read_text(encoding="utf-8")
    catalog = yaml.safe_load(instance_workspace.catalog_path.read_text(encoding="utf-8"))
    assert {entry["id"] for entry in catalog["ensembles"]} == {"boutique", "intranet"}


def test_pin_composition_is_create_exclusive(instance_workspace: Workspace, tmp_path: Path) -> None:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-pin")
    _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            payload={"id": "backend", "kind": "service", "path": str(backend)},
            command_id="CMD-mem-pin-1",
        ),
    )
    _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 2},
            payload={"id": "frontend", "kind": "ui", "path": str(frontend)},
            command_id="CMD-mem-pin-2",
        ),
    )
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "PinComposition",
            target={"kind": "composition", "id": "CR-boutique-1"},
            payload={"id": "CR-boutique-1", "ensemble_id": "boutique"},
            command_id="CMD-pin-1",
        ),
    )
    assert code == 0, receipt
    document = yaml.safe_load(
        (
            instance_workspace.ensembles_root
            / "boutique"
            / "compositions"
            / "CR-boutique-1.yaml"
        ).read_text(encoding="utf-8")
    )
    assert document["kind"] == "composition"
    assert document["members"]["backend"] == head_sha(backend)
    assert document["members"]["frontend"] == head_sha(frontend)
    catalog = yaml.safe_load(instance_workspace.catalog_path.read_text(encoding="utf-8"))
    assert catalog["ensembles"][0]["composition"] == "CR-boutique-1"

    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "PinComposition",
            target={"kind": "composition", "id": "CR-boutique-1"},
            payload={
                "id": "CR-boutique-1",
                "ensemble_id": "boutique",
                "members": {"backend": SHA_A, "frontend": SHA_B},
            },
            command_id="CMD-pin-dup",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value
    persisted = yaml.safe_load(
        (
            instance_workspace.ensembles_root
            / "boutique"
            / "compositions"
            / "CR-boutique-1.yaml"
        ).read_text(encoding="utf-8")
    )
    assert persisted["members"]["backend"] == head_sha(backend)


def test_set_active_ensemble_is_discovered(instance_workspace: Workspace) -> None:
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-act")
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "SetActiveEnsemble",
            target={"kind": "ensemble", "id": "boutique"},
            payload={"ensemble_id": "boutique"},
            command_id="CMD-act-1",
        ),
    )
    assert code == 0, receipt
    rediscovered = Workspace.from_root(instance_workspace.root)
    assert rediscovered.active_ensemble_id == "boutique"


def test_register_ensemble_rejected_for_implementer_role(instance_workspace: Workspace) -> None:
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterEnsemble",
            target={"kind": "ensemble", "id": "boutique"},
            payload={"id": "boutique"},
            command_id="CMD-ens-unauth",
            role_id="backend-developer",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_register_ensemble_rejected_on_framework_source(tmp_path: Path) -> None:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="framework-renov")
    profile = yaml.safe_load((ai_team / "project-profile.yaml").read_text(encoding="utf-8"))
    profile["project"]["repository_kind"] = "framework_source"
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False), encoding="utf-8"
    )
    workspace = Workspace.from_root(tmp_path)
    receipt, code = _execute(
        workspace,
        _envelope(
            "RegisterEnsemble",
            target={"kind": "ensemble", "id": "boutique"},
            payload={"id": "boutique"},
            command_id="CMD-ens-src",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.UNSUPPORTED_CONTRACT.value
    assert not (workspace.ensembles_root / "boutique" / "members.yaml").exists()


def test_gateway_refuses_client_cycle_discovered_from_member(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    _register_ensemble(instance_workspace, "boutique", "CMD-ens-cwd")
    receipt, code = _execute(
        instance_workspace,
        _envelope(
            "RegisterMember",
            target={"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            payload={"id": "backend", "kind": "service", "path": str(backend)},
            command_id="CMD-mem-cwd",
        ),
    )
    assert code == 0, receipt
    discovered = Workspace.discover(backend)
    assert discovered.root == instance_workspace.root
    assert discovered.discovered_member_id == "backend"
    receipt, code = _execute(
        discovered,
        _envelope(
            "RegisterEnsemble",
            target={"kind": "ensemble", "id": "intranet"},
            payload={"id": "intranet"},
            command_id="CMD-ens-from-member",
        ),
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.UNSUPPORTED_CONTRACT.value
    assert str(instance_workspace.root) in receipt["errors"][0]["message"]
    assert not (instance_workspace.ensembles_root / "intranet" / "members.yaml").exists()
