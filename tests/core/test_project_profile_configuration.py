"""Governed Project Profile changes during development."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tests.conftest import PAYLOAD_AI_TEAM

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGURE_PY = REPO_ROOT / "scripts" / "ai-team" / "configure.py"


@pytest.fixture()
def profile_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    shutil.copytree(PAYLOAD_AI_TEAM / "contracts", ai_team / "contracts")
    shutil.copytree(PAYLOAD_AI_TEAM / "schemas", ai_team / "schemas")
    profile = {
        "project": {"id": "sample", "name": "Sample", "repository_kind": "product"},
        "config_revision": 1,
        "autonomy": {"preset": "supervised_copilots"},
        "paths": {},
        "commands": {},
        "runtime_environments": {},
        "release": {},
        "human_authorities": {},
        "setup_status": {"template": False},
        "active_adapter_id": "cursor",
    }
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False), encoding="utf-8"
    )
    (ai_team / "runs").mkdir()
    (ai_team / "runs" / "RUN-existing.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "RUN-existing",
                "revision": 1,
                "status": "active",
                "autonomy_preset": "supervised_copilots",
                "effective_autonomy_policy": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _envelope(**overrides) -> dict:
    value = {
        "protocol_version": "1.0",
        "command_id": "CMD-profile-1",
        "idempotency_key": "idem-profile-1",
        "correlation_id": "COR-profile-1",
        "type": "UpdateProjectProfile",
        "issued_at": "2026-09-11T10:00:00Z",
        "actor": {"kind": "role", "role_id": "control-plane"},
        "target": {"kind": "project_profile", "id": "sample", "expected_revision": 1},
        "payload": {
            "changes": {"autonomy": {"preset": "unattended_conservative"}},
            "reason": "Enable bounded unattended work",
        },
        "human_authorization": {
            "authorization_id": "AUTH-profile-1",
            "granted_by": "Project owner",
        },
    }
    value.update(overrides)
    return value


def test_profile_change_is_transactional_audited_and_future_only(
    profile_workspace: Workspace,
) -> None:
    receipt, exit_code = CommandGateway(profile_workspace).execute_command(_envelope())

    assert exit_code == 0
    assert receipt["status"] == "accepted"
    assert receipt["affected"] == [
        {"kind": "project_profile", "id": "sample", "revision": 2}
    ]
    assert receipt["details"]["effective_scope"] == "future_runs"

    profile = yaml.safe_load(profile_workspace.profile_path.read_text(encoding="utf-8"))
    assert profile["config_revision"] == 2
    assert profile["autonomy"]["preset"] == "unattended_conservative"

    existing_run = yaml.safe_load(
        (profile_workspace.ai_team / "runs" / "RUN-existing.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert existing_run["autonomy_preset"] == "supervised_copilots"

    changes = list((profile_workspace.ai_team / "profile-changes").glob("*.yaml"))
    assert len(changes) == 1
    history = yaml.safe_load(changes[0].read_text(encoding="utf-8"))
    assert history["previous_revision"] == 1
    assert history["new_revision"] == 2
    assert history["changed_by"] == "Project owner"
    assert history["resolved_autonomy_preset"] == "unattended_conservative"

    authorization = json.loads(
        (profile_workspace.ai_team / "authorizations" / "AUTH-profile-1.json").read_text(
            encoding="utf-8"
        )
    )
    assert authorization["consumed_at"]


def test_profile_change_rejects_stale_revision(profile_workspace: Workspace) -> None:
    envelope = _envelope(
        idempotency_key="idem-profile-stale",
        target={"kind": "project_profile", "id": "sample", "expected_revision": 9},
    )
    receipt, exit_code = CommandGateway(profile_workspace).execute_command(envelope)

    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_profile_change_rejects_immutable_sections(profile_workspace: Workspace) -> None:
    envelope = _envelope(
        idempotency_key="idem-profile-immutable",
        payload={"changes": {"project": {"id": "other"}}, "reason": "rename"},
    )
    receipt, exit_code = CommandGateway(profile_workspace).execute_command(envelope)

    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_profile_change_requires_human_authorization(profile_workspace: Workspace) -> None:
    envelope = _envelope(idempotency_key="idem-profile-auth")
    del envelope["human_authorization"]
    receipt, exit_code = CommandGateway(profile_workspace).execute_command(envelope)

    assert exit_code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value


def test_project_profile_query_exposes_legacy_revision(profile_workspace: Workspace) -> None:
    profile = yaml.safe_load(profile_workspace.profile_path.read_text(encoding="utf-8"))
    profile.pop("config_revision")
    profile_workspace.profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    result = CommandGateway(profile_workspace).query("project-profile")

    assert result["data"]["config_revision"] == 1


def test_configure_cli_changes_autonomy(profile_workspace: Workspace) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(CONFIGURE_PY),
            "autonomy",
            "unattended_extended",
            "--reason",
            "Approved wider development window",
            "--authorized-by",
            "Project owner",
        ],
        cwd=profile_workspace.root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "accepted"
    profile = yaml.safe_load(profile_workspace.profile_path.read_text(encoding="utf-8"))
    assert profile["autonomy"]["preset"] == "unattended_extended"
