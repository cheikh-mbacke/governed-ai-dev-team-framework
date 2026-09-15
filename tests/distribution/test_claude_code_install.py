"""Fresh install with --adapter claude-code — installer wiring for a second Adaptateur.

Mirrors tests/distribution/test_install.py's Cursor coverage, plus a
regression pin that the default (no --adapter) path still installs Cursor
unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from adapters.claude_code.compiler.staging import sha256_bytes
from distribution.installer.record import INSTALLATION_RECORD_FILE, is_installation_record

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "tools" / "install.py"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "claude-code-compile" / "golden-manifest.json"


def _run_install(
    target: Path, *, adapter: str | None = None, project_id: str = "claude-code-install-test"
) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(INSTALL),
        "--target",
        str(target),
        "--project-id",
        project_id,
        "--project-name",
        "Claude Code Install Test",
    ]
    if adapter is not None:
        args.extend(["--adapter", adapter])
    return subprocess.run(
        args, cwd=REPO_ROOT, text=True, capture_output=True, timeout=180, check=False
    )


def test_fresh_install_with_adapter_claude_code_materializes_claude_dir(tmp_path: Path) -> None:
    target = tmp_path / "cc"
    result = _run_install(target, adapter="claude-code")
    assert result.returncode == 0, result.stdout + result.stderr

    assert (target / ".claude").is_dir()
    assert (target / ".claude" / "settings.json").is_file()
    assert (target / ".claude" / "hooks" / "guard_shell.py").is_file()
    assert (target / ".claude" / "agents" / "backend-developer.md").is_file()
    assert not (target / ".cursor").exists()

    record = json.loads((target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8"))
    assert is_installation_record(record)
    assert record["active_adapter_id"] == "claude-code"
    assert [a["id"] for a in record["adapters"]] == ["claude-code"]
    assert record["adapters"][0]["managed_files"]

    profile = yaml.safe_load(
        (target / ".ai-team/project-profile.yaml").read_text(encoding="utf-8")
    )
    assert profile.get("active_adapter_id") == "claude-code"


def test_fresh_install_with_adapter_claude_code_matches_golden_manifest(tmp_path: Path) -> None:
    target = tmp_path / "cc-golden"
    result = _run_install(target, adapter="claude-code")
    assert result.returncode == 0, result.stdout + result.stderr

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for entry in golden["artifacts"]:
        path = target / entry["path"]
        assert path.is_file(), entry["path"]
        assert sha256_bytes(path.read_bytes()) == entry["sha256"], entry["path"]


def test_fresh_install_with_adapter_claude_code_passes_validate(tmp_path: Path) -> None:
    target = tmp_path / "cc-validate"
    result = _run_install(target, adapter="claude-code")
    assert result.returncode == 0, result.stdout + result.stderr

    validation = subprocess.run(
        [sys.executable, "scripts/ai-team/validate.py"],
        cwd=target,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr


def test_fresh_install_default_adapter_is_still_cursor(tmp_path: Path) -> None:
    target = tmp_path / "default"
    result = _run_install(target)
    assert result.returncode == 0, result.stdout + result.stderr

    assert (target / ".cursor").is_dir()
    assert not (target / ".claude").exists()
    record = json.loads((target / INSTALLATION_RECORD_FILE).read_text(encoding="utf-8"))
    assert record["active_adapter_id"] == "cursor"


def test_update_flag_rejects_adapter_switch(tmp_path: Path) -> None:
    target = tmp_path / "no-switch"
    install = _run_install(target, adapter="claude-code")
    assert install.returncode == 0, install.stdout + install.stderr

    result = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--update",
            "--adapter",
            "cursor",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "fresh install" in (result.stdout + result.stderr)
