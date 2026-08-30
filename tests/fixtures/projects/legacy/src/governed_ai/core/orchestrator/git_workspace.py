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


def ensure_work_unit_worktree(project_root: Path, run_id: str, work_unit_id: str) -> Path:
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
        args.extend(["-b", branch])
    args.extend([str(path), branch if exists else "HEAD"])
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
