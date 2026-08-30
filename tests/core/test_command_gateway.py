"""Command Gateway infrastructure tests (Document 14 CG-001..CG-005, CG-010)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.persistence.lock import force_release_stale_lock
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV_PY = REPO_ROOT / "scripts" / "ai-team" / "gov.py"


@pytest.fixture()
def gateway_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    contracts = ai_team / "contracts"
    source_contracts = REPO_ROOT / ".ai-team" / "contracts"
    if source_contracts.is_dir():
        shutil.copytree(source_contracts, contracts)
    else:
        published = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
        bundle_dest = contracts / "bundles" / "1.0.0"
        shutil.copytree(published, bundle_dest)
        manifest = json.loads((bundle_dest / "manifest.json").read_text(encoding="utf-8"))
        (contracts / "active-bundle.json").write_text(
            json.dumps(
                {
                    "bundle_version": "1.0.0",
                    "path": "bundles/1.0.0",
                    "content_hash": manifest["content_hash"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    work_units = ai_team / "work-units"
    work_units.mkdir(parents=True)
    (work_units / "WU-GW-TEST.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-GW-TEST",
                "title": "Gateway test work unit",
                "objective": {"result": "test"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "transition under gateway",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "ready",
                "revision": 1,
            }
        ),
        encoding="utf-8",
    )
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text(
        "phase: execution\n",
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _envelope(**overrides) -> dict:
    base = {
        "protocol_version": "1.0",
        "command_id": "CMD-test-001",
        "idempotency_key": "idem-test-001",
        "correlation_id": "COR-test-001",
        "type": "TransitionWorkUnit",
        "issued_at": "2026-08-29T16:00:00Z",
        "actor": {
            "kind": "role",
            "execution_id": "EXE-test",
            "role_id": "control-plane",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        "target": {
            "kind": "work_unit",
            "id": "WU-GW-TEST",
            "expected_revision": 1,
        },
        "payload": {"to_status": "in_progress", "reason": "gateway test"},
    }
    base.update(overrides)
    return base


def test_cg001_accepted_command_creates_transaction(gateway_workspace: Workspace) -> None:
    gateway = CommandGateway(gateway_workspace)
    receipt, exit_code = gateway.execute_command(_envelope())
    assert exit_code == 0
    assert receipt["status"] == "accepted"
    assert receipt["transaction_id"] is not None
    assert receipt["affected"][0]["id"] == "WU-GW-TEST"
    tx_dir = gateway_workspace.ai_team / ".transactions" / receipt["transaction_id"]
    assert (tx_dir / "journal.json").is_file()
    updated = yaml.safe_load(
        (gateway_workspace.ai_team / "work-units" / "WU-GW-TEST.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert updated["status"] == "in_progress"
    assert updated["revision"] == 2


def test_cg002_invalid_payload_rejected_without_mutation(gateway_workspace: Workspace) -> None:
    bad = _envelope()
    del bad["payload"]["to_status"]
    before = (gateway_workspace.ai_team / "work-units" / "WU-GW-TEST.yaml").read_text(
        encoding="utf-8"
    )
    gateway = CommandGateway(gateway_workspace)
    receipt, exit_code = gateway.execute_command(bad)
    assert exit_code == 3
    assert receipt["status"] == "rejected"
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_SCHEMA.value
    assert receipt["errors"][0]["path"] == "/payload/to_status"
    after = (gateway_workspace.ai_team / "work-units" / "WU-GW-TEST.yaml").read_text(
        encoding="utf-8"
    )
    assert before == after


def test_cg003_stale_expected_revision_conflicts(gateway_workspace: Workspace) -> None:
    gateway = CommandGateway(gateway_workspace)
    bad = _envelope()
    bad["target"] = {**bad["target"], "expected_revision": 99}
    receipt, exit_code = gateway.execute_command(bad)
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value
    doc = yaml.safe_load(
        (gateway_workspace.ai_team / "work-units" / "WU-GW-TEST.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert doc["revision"] == 1


def test_cg004_idempotent_replay_returns_same_receipt(gateway_workspace: Workspace) -> None:
    gateway = CommandGateway(gateway_workspace)
    first, code1 = gateway.execute_command(_envelope(idempotency_key="idem-cg004"))
    second, code2 = gateway.execute_command(_envelope(idempotency_key="idem-cg004"))
    assert code1 == code2 == 0
    assert second == first
    doc = yaml.safe_load(
        (gateway_workspace.ai_team / "work-units" / "WU-GW-TEST.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert doc["revision"] == 2


def test_cg005_idempotency_mismatch(gateway_workspace: Workspace) -> None:
    gateway = CommandGateway(gateway_workspace)
    gateway.execute_command(_envelope(idempotency_key="idem-cg005"))
    mutated = _envelope(
        idempotency_key="idem-cg005",
        payload={"to_status": "in_progress", "reason": "different"},
    )
    receipt, exit_code = gateway.execute_command(mutated)
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.IDEMPOTENCY_MISMATCH.value


def test_cg010_cli_stdout_json_only_stderr_diagnostics(gateway_workspace: Workspace) -> None:
    envelope_path = gateway_workspace.root / "command.json"
    envelope_path.write_text(
        json.dumps(_envelope(idempotency_key="idem-cli-010")),
        encoding="utf-8",
    )
    force_release_stale_lock(gateway_workspace.ai_team / "locks" / "project.lock")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, str(GOV_PY), "command", "--input", str(envelope_path)],
        cwd=gateway_workspace.root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0
    stdout = completed.stdout.strip()
    assert stdout
    json.loads(stdout)
    assert not completed.stderr.strip()

    bad = subprocess.run(
        [sys.executable, str(GOV_PY), "query", "missing-query"],
        cwd=gateway_workspace.root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert bad.returncode != 0
    json.loads(bad.stdout)
    assert bad.stderr.strip()
