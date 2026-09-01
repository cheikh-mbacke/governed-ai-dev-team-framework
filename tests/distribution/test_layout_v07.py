"""Layout v0.7, collision, AGENTS.md merge, dry-run and rollback tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from distribution.installer.agents_md import MARKER_END, MARKER_START, merge_agents_md
from distribution.installer.migrate_layout import apply_layout_migration
from distribution.installer.record import INSTALLATION_RECORD_FILE, is_v3_record

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"


def _run_install(
    target: Path,
    *,
    project_id: str = "layout-test",
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        str(INSTALL),
        "--target",
        str(target),
        "--project-id",
        project_id,
        "--project-name",
        "Layout Test",
    ]
    if extra_args:
        command.extend(extra_args)
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def _run_update(target: Path, *extra: str) -> subprocess.CompletedProcess:
    command = [sys.executable, str(INSTALL), "--target", str(target), "--update", *extra]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def test_fresh_install_succeeds_on_ordinary_brownfield_project(tmp_path: Path) -> None:
    # The Document 11 §4 copy map no longer writes into src/, docs/, README.md
    # or root requirements.txt at all, so an ordinary project using those
    # names (the common case this whole layout change targets) must install
    # cleanly, with its own content left byte-for-byte untouched.
    target = tmp_path / "brownfield"
    target.mkdir()
    (target / "README.md").write_text("# My App\n", encoding="utf-8")
    (target / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (target / "src").mkdir()
    (target / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (target / "docs").mkdir()
    (target / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")

    result = _run_install(target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "README.md").read_text(encoding="utf-8") == "# My App\n"
    assert (target / "requirements.txt").read_text(encoding="utf-8") == "flask\n"
    assert (target / "src" / "app.py").read_text(encoding="utf-8") == "print('app')\n"
    assert (target / "docs" / "guide.md").read_text(encoding="utf-8") == "guide\n"
    assert (target / ".ai-team" / "installation-record.json").exists()


def test_fresh_install_aborts_on_real_file_collision(tmp_path: Path) -> None:
    target = tmp_path / "cursor-collision"
    target.mkdir()
    (target / ".cursor").mkdir()
    (target / ".cursor" / "cli.json").write_text('{"sentinel": true}\n', encoding="utf-8")

    result = _run_install(target)
    assert result.returncode == 2
    assert "Collision report" in result.stdout
    assert (target / ".cursor" / "cli.json").read_text(encoding="utf-8") == '{"sentinel": true}\n'
    assert not (target / ".ai-team" / "installation-record.json").exists()


def test_fresh_install_aborts_on_legacy_framework_fingerprint(tmp_path: Path) -> None:
    target = tmp_path / "legacy-fingerprint"
    target.mkdir()
    (target / "src" / "governed_ai").mkdir(parents=True)
    (target / "src" / "governed_ai" / "__init__.py").write_text("", encoding="utf-8")

    result = _run_install(target)
    assert result.returncode == 2
    assert "Collision report" in result.stdout
    assert "use --update" in result.stdout
    assert not (target / ".ai-team" / "installation-record.json").exists()


def test_fresh_install_preserves_existing_agents_md_content(tmp_path: Path) -> None:
    target = tmp_path / "agents-merge"
    target.mkdir()
    (target / "AGENTS.md").write_text("# Team rules\nKeep this.\n", encoding="utf-8")

    result = _run_install(target)
    assert result.returncode == 0, result.stdout + result.stderr
    merged = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep this." in merged
    assert MARKER_START in merged
    assert MARKER_END in merged
    assert "Governed AI Team Instructions" in merged


def test_agents_md_merge_unit() -> None:
    existing = "# Header\n\nUser content.\n"
    managed = "Managed body"
    merged = merge_agents_md(existing, managed)
    assert "User content." in merged
    assert MARKER_START in merged
    assert "Managed body" in merged


def test_fresh_install_uses_runtime_layout(tmp_path: Path) -> None:
    target = tmp_path / "runtime-layout"
    result = _run_install(target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / ".ai-team" / "runtime" / "governed_ai" / "core").is_dir()
    assert (target / ".ai-team" / "requirements.txt").is_file()
    assert not (target / "src" / "governed_ai").exists()
    assert not (target / "README.md").exists()
    record = json.loads((target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8"))
    assert is_v3_record(record)


def test_dry_run_legacy_v1_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "legacy-dry"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "projects" / "legacy", target)
    v2 = target / INSTALLATION_RECORD_FILE
    if v2.is_file():
        v2.unlink()
    legacy = target / ".ai-team" / "framework-version.json"
    assert legacy.is_file()
    before = legacy.read_bytes()

    proc = _run_update(target, "--dry-run", "--force-constitution-update")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert legacy.read_bytes() == before
    assert not (target / INSTALLATION_RECORD_FILE).exists()


def test_install_rollback_on_interrupted_copy(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "rollback-install"
    target.mkdir()
    (target / "src").mkdir()
    (target / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")

    from argparse import Namespace

    from distribution.installer import build_record

    def boom(*args, **kwargs):
        raise OSError("simulated install interruption")

    monkeypatch.setattr(build_record, "finalize_installation_manifests", boom)

    from distribution.installer.operations import install_fresh

    args = Namespace(
        project_id="rollback-test",
        project_name="Rollback Test",
        force=True,
    )
    result = install_fresh(REPO_ROOT, args, target)
    assert result == 1
    assert not (target / INSTALLATION_RECORD_FILE).exists()


def test_local_drift_detected_on_update(tmp_path: Path) -> None:
    target = tmp_path / "drift"
    assert _run_install(target).returncode == 0
    record = json.loads((target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8"))
    assert is_v3_record(record)

    schema = target / ".ai-team" / "schemas" / "work-unit.schema.json"
    schema.write_text("{}\n", encoding="utf-8")

    proc = _run_update(target, "--skip-validation")
    assert proc.returncode == 2
    assert "local_drift" in proc.stdout.lower() or "local drift" in proc.stdout.lower()


def test_layout_migration_moves_unambiguous_paths(tmp_path: Path) -> None:
    target = tmp_path / "layout-migrate"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "projects" / "legacy", target)

    legacy_core = target / "src" / "governed_ai" / "core"
    assert legacy_core.is_dir()

    result = apply_layout_migration(target, version_from="0.6.0", version_to="0.7.0")
    assert (target / ".ai-team" / "runtime" / "governed_ai" / "core").is_dir()
    assert any(src == "src/governed_ai" for src, _dest in result.moved)


def test_layout_migration_emits_forensic_event_for_ambiguous_root_files(tmp_path: Path) -> None:
    target = tmp_path / "forensic"
    _run_install(target)
    assert (target / "AGENTS.md").is_file()

    # Simulate legacy root requirements after a prior overwrite scenario.
    (target / "requirements.txt").write_text("legacy-root-req\n", encoding="utf-8")

    result = apply_layout_migration(target, version_from="0.6.0", version_to="0.7.0")
    assert result.forensic_events
    event_text = result.forensic_events[0].read_text(encoding="utf-8")
    assert "DECISION_REQUEST" in event_text
    assert "requirements.txt" in event_text
    assert (target / "requirements.txt").read_text(encoding="utf-8") == "legacy-root-req\n"
