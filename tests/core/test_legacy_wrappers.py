"""WU-P3-LEGACY-WRAPPERS — legacy CLI translation and gateway wrappers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import EXIT_CLI
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.commands.legacy_cli import (
    DEPRECATION_FEEDBACK,
    FeedbackExportArgs,
    FeedbackRecordArgs,
    RecordGateArgs,
    TranslationError,
    format_feedback_record_stdout,
    translate_feedback_export,
    translate_feedback_record,
    translate_record_gate,
)
from governed_ai.core.workspace import Workspace

from tests.core.workspace_helpers import FABRIC_ROOT, PAYLOAD_AI_TEAM, write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def wrapper_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="wrapper-test")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    for directory in (
        "observations",
        "retrospectives",
        "metrics",
        "decisions",
        "state",
        "authorizations",
        "work-units",
        "locks",
    ):
        (ai_team / directory).mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text(
        yaml.safe_dump({"project_id": "wrapper-test", "phase": "execution", "gates": {}}),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def test_translate_record_gate_requires_authorization() -> None:
    with pytest.raises(TranslationError, match="authorization-id"):
        translate_record_gate(
            RecordGateArgs(
                gate="G2",
                status="not_required",
                by="alice",
                note="test",
            )
        )


def test_translate_feedback_export_full_requires_authorization() -> None:
    with pytest.raises(TranslationError, match="authorization-id"):
        translate_feedback_export(FeedbackExportArgs(detail_level="full"))


def test_record_gate_wrapper_executes_via_gateway(wrapper_workspace: Workspace) -> None:
    envelope = translate_record_gate(
        RecordGateArgs(
            gate="G2",
            status="not_required",
            by="wrapper-test",
            authorization_id="HAUTH-wrapper-g2",
        )
    )
    gateway = CommandGateway(wrapper_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert receipt["affected"][0]["kind"] == "gate_decision"
    assert (wrapper_workspace.ai_team / "decisions" / f"{receipt['affected'][0]['id']}.yaml").is_file()


def test_feedback_record_wrapper_executes_via_gateway(wrapper_workspace: Workspace) -> None:
    envelope = translate_feedback_record(
        FeedbackRecordArgs(category="tooling", symptom="wrapper friction")
    )
    gateway = CommandGateway(wrapper_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    observation_id = receipt["affected"][0]["id"]
    assert (wrapper_workspace.ai_team / "observations" / f"{observation_id}.yaml").is_file()
    stdout = format_feedback_record_stdout(receipt, lang="en")
    assert observation_id in stdout


def test_feedback_export_script_translation_failure_exits_before_gateway(
    wrapper_workspace: Workspace,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "ai-team" / "feedback.py"),
            "export",
            "--detail-level",
            "full",
        ],
        cwd=wrapper_workspace.root,
        text=True,
        capture_output=True,
    )
    assert result.returncode == EXIT_CLI
    assert "authorization-id" in result.stderr
    assert DEPRECATION_FEEDBACK in result.stderr
    assert not list((wrapper_workspace.ai_team / "metrics").glob("*.json"))
