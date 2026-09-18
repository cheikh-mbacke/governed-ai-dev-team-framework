"""Phase 2: member Git isolation and worktrees hosted on the instance."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from governed_ai.core.commands.errors import GatewayError
from governed_ai.core.orchestrator.git_workspace import (
    ensure_work_unit_worktree,
    head_sha,
)
from governed_ai.core.persistence.paths import resolve_under_member, resolve_under_root


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


def test_standalone_worktree_path_unchanged(tmp_path: Path) -> None:
    root = _repository(tmp_path / "app", "app.py", "print(1)\n")
    worker = ensure_work_unit_worktree(root, "RUN-S", "WU-A")
    assert worker == root / ".ai-team" / "worktrees" / "RUN-S" / "WU-A"
    assert (worker / "app.py").is_file()


def test_member_worktree_lives_on_instance_and_does_not_touch_sibling(
    tmp_path: Path,
) -> None:
    instance = tmp_path / "acme-ai-team"
    instance.mkdir()
    (instance / ".ai-team").mkdir()
    backend = _repository(tmp_path / "boutique-api", "api.py", "def ping():\n    return 1\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    backend_sha = head_sha(backend)

    worker = ensure_work_unit_worktree(
        frontend,
        "RUN-FE",
        "WU-PAGE",
        worktree_home=instance,
        ensemble_id="boutique",
    )
    assert worker == (
        instance / ".ai-team" / "worktrees" / "boutique" / "RUN-FE" / "WU-PAGE"
    )
    assert (worker / "page.js").is_file()
    assert not (worker / "api.py").exists()

    (worker / "page.js").write_text("export default { ok: true }\n", encoding="utf-8")
    _git(worker, "add", "page.js")
    _git(worker, "commit", "-m", "feat(WU-PAGE): page")

    assert (backend / "api.py").read_text(encoding="utf-8") == "def ping():\n    return 1\n"
    assert head_sha(backend) == backend_sha
    assert not (frontend / "src").exists()


def test_member_path_escape_to_sibling_is_rejected(tmp_path: Path) -> None:
    frontend = tmp_path / "boutique-web"
    backend = tmp_path / "boutique-api"
    frontend.mkdir()
    backend.mkdir()
    (frontend / "src").mkdir()
    (backend / "src").mkdir()
    (backend / "src" / "secret.py").write_text("nope\n", encoding="utf-8")

    with pytest.raises(GatewayError, match="path traversal"):
        resolve_under_root(frontend, "../boutique-api/src/secret.py")
    with pytest.raises(GatewayError, match="path traversal"):
        resolve_under_member(
            frontend,
            "../boutique-api/src/secret.py",
            instance_root=tmp_path / "acme-ai-team",
            other_member_roots=[backend],
        )


def test_resolve_under_member_keeps_in_tree_paths(tmp_path: Path) -> None:
    frontend = tmp_path / "web"
    backend = tmp_path / "api"
    instance = tmp_path / "hub"
    frontend.mkdir()
    backend.mkdir()
    instance.mkdir()
    resolved = resolve_under_member(
        frontend,
        "src/app.js",
        instance_root=instance,
        other_member_roots=[backend],
    )
    assert resolved == (frontend / "src" / "app.js").resolve()
