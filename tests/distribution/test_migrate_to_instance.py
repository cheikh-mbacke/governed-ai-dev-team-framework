"""Phase 8: opt-in in-tree → instance migration and INS-AC-018 (--update stays standalone)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from distribution.installer.migrate_to_instance import (
    InstanceMigrationError,
    migrate_in_tree_to_instance,
)

from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"
MIGRATE = REPO_ROOT / "tools" / "migrate_to_instance.py"


def _install(target: Path, project_id: str = "boutique") -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            project_id,
            "--project-name",
            "Boutique",
            "--skip-assessment-gate",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _git_init(target: Path) -> None:
    commands = [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.name", "Migration Test"],
        ["git", "config", "user.email", "migration-test@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=target, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr + result.stdout


def test_ins_ac_018_update_without_migrate_leaves_standalone(tmp_path: Path) -> None:
    """``--update`` must not invent an out-of-tree layout (INS-AC-018 / INS-F-014)."""
    source = tmp_path / "standalone-app"
    source.mkdir()
    (source / "app.py").write_text("print(1)\n", encoding="utf-8")
    _install(source)
    _git_init(source)

    proc = subprocess.run(
        [sys.executable, str(INSTALL), "--target", str(source), "--update"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    assert not (source / ".ai-team" / "member-link.json").exists()
    assert (source / ".ai-team" / "installation-record.json").is_file()
    workspace = Workspace.from_root(source)
    assert workspace.instance_root == source.resolve()
    assert workspace.member_root() == source.resolve()
    assert workspace.active_ensemble_id is None


def test_migrate_in_tree_to_instance_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "boutique-api"
    instance = tmp_path / "acme-ai-team"
    source.mkdir()
    (source / "api.py").write_text("def ping():\n    return 1\n", encoding="utf-8")
    _install(source, project_id="boutique")
    _git_init(source)
    (source / ".ai-team" / "state" / "project-state.yaml").write_text(
        "project_id: boutique\nphase: execution\n",
        encoding="utf-8",
    )

    result = migrate_in_tree_to_instance(
        source=source,
        instance=instance,
        ensemble_id="boutique",
        member_id="backend",
        member_kind="service",
        instance_id="acme-ai-team",
    )
    assert result["status"] == "migrated"
    assert (instance / ".ai-team" / "installation-record.json").is_file()
    assert (instance / ".ai-team" / "ensembles" / "boutique" / "members.yaml").is_file()
    assert (instance / ".ai-team" / "active-ensemble.yaml").is_file()
    assert (source / ".ai-team" / "member-link.json").is_file()
    assert not (source / ".ai-team" / "installation-record.json").exists()
    assert not (source / ".cursor").exists()

    link = json.loads((source / ".ai-team" / "member-link.json").read_text(encoding="utf-8"))
    assert link["ensemble_id"] == "boutique"
    assert link["member_id"] == "backend"
    assert Path(link["instance_path"]).resolve() == instance.resolve()

    workspace = Workspace.from_root(instance)
    assert workspace.active_ensemble_id == "boutique"
    assert workspace.member_root("backend") == source.resolve()
    assert workspace.instance_root == instance.resolve()

    members = yaml.safe_load(
        (instance / ".ai-team" / "ensembles" / "boutique" / "members.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert members["members"][0]["id"] == "backend"
    state = (instance / ".ai-team" / "ensembles" / "boutique" / "state" / "project-state.yaml")
    assert state.is_file()
    assert "execution" in state.read_text(encoding="utf-8")


def test_migrate_rollback_on_failure(tmp_path: Path) -> None:
    source = tmp_path / "app"
    instance = tmp_path / "hub"
    source.mkdir()
    (source / "main.py").write_text("x = 1\n", encoding="utf-8")
    _install(source, project_id="app")
    _git_init(source)
    before_record = (source / ".ai-team" / "installation-record.json").read_text(encoding="utf-8")

    with pytest.raises(InstanceMigrationError, match="fail_after=move"):
        migrate_in_tree_to_instance(
            source=source,
            instance=instance,
            ensemble_id="app",
            member_id="app",
            fail_after="move",
        )

    assert (source / ".ai-team" / "installation-record.json").is_file()
    assert (source / ".ai-team" / "installation-record.json").read_text(
        encoding="utf-8"
    ) == before_record
    assert not (source / ".ai-team" / "member-link.json").exists()
    assert not instance.exists() or not (instance / ".ai-team").exists()


def test_migrate_cli_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "app"
    instance = tmp_path / "hub"
    source.mkdir()
    _install(source, project_id="app")
    _git_init(source)

    proc = subprocess.run(
        [
            sys.executable,
            str(MIGRATE),
            "--source",
            str(source),
            "--instance",
            str(instance),
            "--ensemble-id",
            "app",
            "--member-id",
            "app",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "dry_run"
    assert (source / ".ai-team" / "installation-record.json").is_file()
    assert not instance.exists()
