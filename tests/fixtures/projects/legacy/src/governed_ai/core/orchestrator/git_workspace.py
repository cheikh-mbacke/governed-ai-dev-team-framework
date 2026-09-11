"""Isolated Git workspaces for unattended workers and the integration queue."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


class GitWorkspaceError(RuntimeError):
    pass


def _safe(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not safe:
        raise GitWorkspaceError("empty identifier after Git branch sanitization")
    return safe


def _run(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={project_root}", *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise GitWorkspaceError((completed.stderr or completed.stdout).strip())
    return completed


def head_sha(workspace_root: Path) -> str:
    value = _run(workspace_root, ["rev-parse", "HEAD"]).stdout.strip().lower()
    if len(value) != 40:
        raise GitWorkspaceError("Git did not return a full commit SHA")
    return value


def changed_files(workspace_root: Path, base_sha: str, result_sha: str) -> list[str]:
    completed = _run(
        workspace_root,
        ["diff", "--name-only", "--no-renames", f"{base_sha}..{result_sha}"],
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def list_uncommitted_files(workspace_root: Path) -> list[str]:
    """Return paths from ``git status --porcelain`` (uncommitted work only)."""
    status = _run(workspace_root, ["status", "--porcelain"]).stdout
    files: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        meta = line[:2]
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[-1]
        # Quoted paths from git when special chars are present.
        if path_part.startswith('"') and path_part.endswith('"'):
            path_part = path_part[1:-1]
        path = path_part.replace("\\", "/")
        if path and path not in files:
            files.append(path)
        _ = meta
    return files


def create_unverified_wip_commit(
    workspace_root: Path,
    *,
    work_unit_id: str,
    paths: list[str] | None = None,
    message_suffix: str = "timeout WIP checkpoint",
) -> str | None:
    """Stage pre-validated dirty paths into an explicit unverified WIP commit.

    Callers must boundary-check ``paths`` before invoking this helper. Returns
    the new HEAD SHA when a commit was created, else None.
    """
    to_add = list(paths) if paths is not None else list_uncommitted_files(workspace_root)
    if not to_add:
        return None
    _run(workspace_root, ["add", "--", *to_add])
    staged = _run(workspace_root, ["diff", "--cached", "--name-only"]).stdout.strip()
    if not staged:
        return None
    message = f"wip({work_unit_id}): {message_suffix} [unverified]"
    _run(
        workspace_root,
        [
            "-c",
            "user.email=governed-ai@local",
            "-c",
            "user.name=Governed AI",
            "commit",
            "--no-gpg-sign",
            "-m",
            message,
        ],
    )
    return head_sha(workspace_root)


def ensure_work_unit_worktree(
    project_root: Path,
    run_id: str,
    work_unit_id: str,
    *,
    start_sha: str | None = None,
) -> Path:
    run_key = _safe(run_id)
    wu_key = _safe(work_unit_id)
    path = project_root / ".ai-team" / "worktrees" / run_key / wu_key
    if (path / ".git").exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    branch = f"ai-run/{run_key}/{wu_key}"
    exists = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={project_root}",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        cwd=str(project_root),
        capture_output=True,
        timeout=10,
        check=False,
    ).returncode == 0
    args = ["worktree", "add"]
    if not exists:
        start_point = start_sha or "HEAD"
        if start_sha:
            # Ensure the SHA is known locally before branching from it.
            _run(project_root, ["cat-file", "-e", f"{start_sha}^{{commit}}"])
        args.extend(["-b", branch, str(path), start_point])
    else:
        args.extend([str(path), branch])
    _run(project_root, args)
    return path


def ensure_integration_worktree(project_root: Path, run_id: str, branch: str) -> Path:
    run_key = _safe(run_id)
    path = project_root / ".ai-team" / "worktrees" / run_key / "_integration"
    if (path / ".git").exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={project_root}",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        cwd=str(project_root),
        capture_output=True,
        timeout=10,
        check=False,
    ).returncode == 0
    args = ["worktree", "add"]
    if not exists:
        args.extend(["-b", branch])
    args.extend([str(path), branch if exists else "HEAD"])
    _run(project_root, args)
    return path


def merge_and_revalidate(
    project_root: Path,
    *,
    run_id: str,
    work_unit_id: str,
    integration_branch: str,
    verification_command: str,
) -> tuple[str, str]:
    """Merge the isolated WU branch and return (merge_sha, evidence_digest)."""
    integration_root = ensure_integration_worktree(project_root, run_id, integration_branch)
    candidate_branch = f"ai-run/{_safe(run_id)}/{_safe(work_unit_id)}"
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={integration_root}",
            "merge",
            "--no-ff",
            "--no-edit",
            candidate_branch,
        ],
        cwd=str(integration_root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={integration_root}",
                "merge",
                "--abort",
            ],
            cwd=str(integration_root),
            capture_output=True,
            timeout=30,
            check=False,
        )
        raise GitWorkspaceError(
            f"integration conflict: {(completed.stderr or completed.stdout).strip()}"
        )
    verification = subprocess.run(
        verification_command,
        cwd=str(integration_root),
        capture_output=True,
        text=True,
        timeout=900,
        shell=True,
        check=False,
    )
    transcript = f"{verification.stdout}\n{verification.stderr}".encode()
    evidence_digest = f"sha256:{hashlib.sha256(transcript).hexdigest()}"
    if verification.returncode != 0:
        raise GitWorkspaceError("full integration revalidation failed")
    return head_sha(integration_root), evidence_digest
