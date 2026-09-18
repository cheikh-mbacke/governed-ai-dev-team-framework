"""Transactional workspace — promote commits only after Core validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.domain.run.path_policy import (
    CONTROL_PLANE_ONLY_PATH_PREFIXES,
    normalize_repo_path,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.execution_gateway.security import (
    assert_no_escaping_link,
    assert_not_control_plane,
    assert_relative_workspace_path,
)
from governed_ai.core.orchestrator.boundary import boundary_error_for_changed_files
from governed_ai.core.orchestrator.git_workspace import (
    GitWorkspaceError,
    changed_files,
    head_sha,
    list_uncommitted_files,
)
from governed_ai.core.persistence.atomic import atomic_write_text

EPHEMERAL_META_SUFFIX = ".meta.json"
TRANSACTION_IGNORE = (
    ".governed-ephemeral.json",
    ".ai-team/supervisor/",
)


def _git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"safe.directory={project_root}",
            *args,
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise GitWorkspaceError((completed.stderr or completed.stdout).strip())
    return completed


def ephemeral_meta_path(project_root: Path, execution_id: str) -> Path:
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in execution_id)
    return project_root / ".ai-team" / "supervisor" / "ephemeral" / f"{safe_id}{EPHEMERAL_META_SUFFIX}"


def create_ephemeral_workspace(
    project_root: Path,
    *,
    base_sha: str,
    execution_id: str,
    worktree_home: Path | None = None,
) -> Path:
    """Create an ephemeral worktree; metadata lives outside the candidate git tree."""
    git_root = Path(project_root).resolve()
    home = Path(worktree_home or git_root).resolve()
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in execution_id)
    path = home / ".ai-team" / "supervisor" / "ephemeral" / safe_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    branch = f"ai-ephemeral/{safe_id}-{uuid.uuid4().hex[:8]}"
    _git(
        git_root,
        ["worktree", "add", "-b", branch, str(path), base_sha],
    )
    marker = {
        "schema_version": 1,
        "execution_id": execution_id,
        "base_sha": base_sha,
        "branch": branch,
        "worktree": str(path),
        "promotable": False,
        "resumable": False,
    }
    # Metadata is Control-Plane only — never inside the worktree candidate tree.
    atomic_write_text(ephemeral_meta_path(home, execution_id), json.dumps(marker, indent=2) + "\n")
    return path


def _is_transaction_metadata(path: str) -> bool:
    normalized = path.replace("\\", "/").strip().rstrip("/")
    if normalized == ".governed-ephemeral.json":
        return True
    if normalized.startswith(".ai-team/supervisor/"):
        return True
    return False


def _is_control_plane_path(path: str) -> bool:
    """Grant/state/runs files are Control Plane — never product candidate diffs."""
    normalized = normalize_repo_path(path)
    if not normalized.endswith("/"):
        # Directory entries from git status may omit the trailing slash.
        as_dir = f"{normalized}/"
    else:
        as_dir = normalized
    return any(
        normalized.startswith(prefix) or as_dir.startswith(prefix) or normalized.rstrip("/") == prefix.rstrip("/")
        for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES
    )


def _expand_to_files(workspace_root: Path, path: str) -> list[str]:
    normalized = path.replace("\\", "/").strip().rstrip("/")
    absolute = workspace_root / normalized
    if absolute.is_dir():
        return [
            child.relative_to(workspace_root).as_posix()
            for child in absolute.rglob("*")
            if child.is_file()
        ]
    if absolute.is_file() or absolute.is_symlink():
        return [normalized]
    # Untracked path may have been deleted between status and expand.
    return [normalized] if normalized else []


def _control_plane_entry_fingerprint(path: Path) -> str:
    """Hash a Control-Plane entry without following an escaping link."""
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    try:
        resolved = path.resolve()
    except OSError as exc:
        return f"unreadable:{type(exc).__name__}"
    if path.is_dir():
        # On Windows a junction is not necessarily reported as a symlink. Its
        # resolved target is security-relevant even though directory contents
        # may be unchanged.
        return f"directory:{resolved}"
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return f"unreadable:{type(exc).__name__}"
    return f"file:{len(payload)}:{hashlib.sha256(payload).hexdigest()}"


def list_control_plane_dirty(workspace_root: Path) -> dict[str, str]:
    """Snapshot every Control-Plane entry, including Git-ignored paths.

    The historical name is retained for API compatibility. Using ``git
    status`` here is insufficient because installed projects intentionally
    ignore mutable ``.ai-team/state`` and supervisor metadata. A verification
    command must not be able to mutate those paths invisibly.
    """
    snapshot: dict[str, str] = {}
    root = workspace_root.resolve()
    for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES:
        relative = prefix.rstrip("/")
        candidate = workspace_root / relative
        if not candidate.exists() and not candidate.is_symlink():
            continue
        entries = [candidate]
        if candidate.is_dir() and not candidate.is_symlink():
            try:
                entries.extend(candidate.rglob("*"))
            except OSError:
                pass
        for entry in entries:
            try:
                rel = entry.relative_to(workspace_root).as_posix()
            except ValueError:
                rel = relative
            snapshot[rel] = _control_plane_entry_fingerprint(entry)
            # Record an escaping directory target without traversing it. The
            # comparison below will reject a newly introduced junction, while
            # the value also detects replacement of an existing directory.
            try:
                entry.resolve().relative_to(root)
            except (OSError, ValueError):
                snapshot[rel] = f"escaping:{snapshot[rel]}"
    return snapshot


def assert_no_new_control_plane_paths(
    workspace_root: Path,
    *,
    preexisting: Mapping[str, str] | set[str],
) -> None:
    """Refuse any Control-Plane mutation after the pre-adapter snapshot."""
    current = list_control_plane_dirty(workspace_root)
    if isinstance(preexisting, Mapping):
        before = dict(preexisting)
    else:
        # Compatibility for callers holding an old path-only snapshot.
        before = {path: current.get(path, "present") for path in preexisting}
    introduced = sorted(set(current) - set(before))
    removed = sorted(set(before) - set(current))
    modified = sorted(
        path for path in set(current) & set(before) if current[path] != before[path]
    )
    changed = [*introduced, *removed, *modified]
    if not changed:
        return
    raise ExecutionGatewayError(
        StructuredError(
            code="forbidden_control_plane_path",
            message=f"Control Plane path mutation forbidden: {changed[0]}",
            path=changed[0],
            details={
                "introduced": introduced,
                "removed": removed,
                "modified": modified,
            },
        )
    )


def inspect_changed_paths(
    workspace_root: Path,
    base_sha: str,
    *,
    ignore_control_plane: bool = True,
    preexisting_control_plane: set[str] | None = None,
) -> list[str]:
    """Inspect uncommitted + committed-since-base changes without trusting the agent.

    Control-Plane paths are excluded from the product candidate set. Callers that
    need to refuse *new* Control-Plane writes should use
    ``assert_no_new_control_plane_paths`` with a pre-adapter snapshot.
    """
    del preexisting_control_plane  # retained for call-site compatibility
    files = set(list_uncommitted_files(workspace_root))
    try:
        current = head_sha(workspace_root)
        if current != base_sha:
            files.update(changed_files(workspace_root, base_sha, current))
    except GitWorkspaceError:
        pass
    cleaned: list[str] = []
    for path in sorted(files):
        normalized = path.replace("\\", "/").strip().rstrip("/")
        if _is_transaction_metadata(normalized):
            continue
        if ignore_control_plane and _is_control_plane_path(normalized):
            continue
        absolute = workspace_root / normalized
        if absolute.is_dir():
            for child in absolute.rglob("*"):
                if not child.is_file():
                    continue
                rel = child.relative_to(workspace_root).as_posix()
                if _is_transaction_metadata(rel):
                    continue
                if ignore_control_plane and _is_control_plane_path(rel):
                    continue
                if rel not in cleaned:
                    cleaned.append(rel)
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def snapshot_workspace_fingerprint(
    workspace_root: Path,
    files: list[str],
) -> dict[str, Any]:
    """Capture content hashes, sizes, and link identity for TOCTOU re-check."""
    entries: dict[str, dict[str, Any]] = {}
    for rel in files:
        absolute = workspace_root / rel
        meta: dict[str, Any] = {
            "exists": absolute.exists(),
            "is_symlink": absolute.is_symlink() if absolute.exists() or absolute.is_symlink() else False,
        }
        if absolute.is_file() and not absolute.is_symlink():
            data = absolute.read_bytes()
            meta["size"] = len(data)
            meta["sha256"] = hashlib.sha256(data).hexdigest()
        elif absolute.is_symlink():
            try:
                meta["link_target"] = os_readlink(absolute)
            except OSError:
                meta["link_target"] = None
        entries[rel] = meta
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"files": entries, "fingerprint": f"sha256:{digest}"}


def os_readlink(path: Path) -> str:
    import os

    return os.readlink(path)


def assert_fingerprint_unchanged(
    workspace_root: Path,
    expected: dict[str, Any],
) -> None:
    files = list((expected.get("files") or {}).keys())
    observed = snapshot_workspace_fingerprint(workspace_root, files)
    # Also refuse newly dirty paths outside the frozen set.
    dirty = [
        path.replace("\\", "/")
        for path in list_uncommitted_files(workspace_root)
        if not _is_transaction_metadata(path.replace("\\", "/"))
        and not _is_control_plane_path(path.replace("\\", "/"))
    ]
    file_set = set(files)
    extra: list[str] = []
    for path in dirty:
        if path in file_set:
            continue
        # Directory parents reported by git status are not mutations when their
        # children were already captured in the frozen file set.
        if any(child == path or child.startswith(path.rstrip("/") + "/") for child in file_set):
            continue
        if any(path.startswith(parent.rstrip("/") + "/") for parent in file_set):
            continue
        extra.append(path)
    if extra:
        raise ExecutionGatewayError(
            StructuredError(
                code="workspace_mutated_after_verification",
                message="workspace gained paths after verification",
                path="workspace.diff",
                details={"extra": extra[:50]},
            )
        )
    if observed.get("fingerprint") != expected.get("fingerprint"):
        raise ExecutionGatewayError(
            StructuredError(
                code="workspace_mutated_after_verification",
                message="workspace content changed after verification",
                path="workspace.diff",
                details={
                    "expected": expected.get("fingerprint"),
                    "observed": observed.get("fingerprint"),
                },
            )
        )


def validate_paths_against_scope(
    files: list[str],
    *,
    work_unit_id: str,
    work_unit: dict[str, Any],
    allowed_paths: list[str],
    workspace_root: Path | None = None,
    role_write_paths: list[str] | None = None,
) -> None:
    for path in files:
        assert_not_control_plane(path)
        if workspace_root is not None:
            assert_relative_workspace_path(workspace_root, path)
            assert_no_escaping_link(workspace_root, path)
    error = boundary_error_for_changed_files(
        files,
        work_unit_id=work_unit_id,
        wu_document=work_unit,
        allowed_paths=allowed_paths,
        role_write_paths=role_write_paths,
    )
    if error:
        message, stop = error
        raise ExecutionGatewayError(
            StructuredError(
                code="scope_violation",
                message=message,
                path="workspace.diff",
                details={"stop_condition": stop, "files": files},
            )
        )


def create_governed_commit(
    workspace_root: Path,
    *,
    work_unit_id: str,
    execution_id: str,
    paths: list[str] | None = None,
    message: str | None = None,
) -> str:
    """Create the governed commit from explicitly validated paths only."""
    validated = [
        path.replace("\\", "/").strip()
        for path in (paths if paths is not None else list_uncommitted_files(workspace_root))
        if path and not _is_transaction_metadata(path.replace("\\", "/"))
    ]
    if validated:
        _git(workspace_root, ["add", "--", *validated])
    staged = [
        line.strip().replace("\\", "/")
        for line in _git(workspace_root, ["diff", "--cached", "--name-only"]).stdout.splitlines()
        if line.strip()
    ]
    illegal = [path for path in staged if _is_transaction_metadata(path) or path not in set(validated)]
    if illegal:
        _git(workspace_root, ["reset", "HEAD", "--", *illegal])
        raise ExecutionGatewayError(
            StructuredError(
                code="illegal_staged_path",
                message="refusing to commit paths outside the validated set",
                path="workspace.commit",
                details={"illegal": illegal},
            )
        )
    staged = [
        line.strip().replace("\\", "/")
        for line in _git(workspace_root, ["diff", "--cached", "--name-only"]).stdout.splitlines()
        if line.strip()
    ]
    if not staged:
        return head_sha(workspace_root)
    commit_message = message or f"feat({work_unit_id}): governed execution {execution_id}"
    _git(
        workspace_root,
        [
            "-c",
            "user.email=governed-ai@local",
            "-c",
            "user.name=Governed AI",
            "commit",
            "--no-gpg-sign",
            "-m",
            commit_message,
        ],
    )
    return head_sha(workspace_root)


def tree_paths_at(workspace_root: Path, sha: str) -> list[str]:
    output = _git(workspace_root, ["ls-tree", "-r", "--name-only", sha]).stdout
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def assert_commit_matches_candidate(
    workspace_root: Path,
    *,
    base_sha: str,
    promoted_sha: str,
    validated_paths: list[str],
    artifact_hashes: dict[str, str],
) -> None:
    """Re-read the commit object and prove it contains exactly the candidate.

    This post-commit check also catches hooks or concurrent index changes. A
    failed check leaves only an unpromoted ephemeral commit, which the caller
    quarantines and makes mechanically non-resumable.
    """
    committed = set(changed_files(workspace_root, base_sha, promoted_sha))
    expected = {path.replace("\\", "/") for path in validated_paths}
    if committed != expected:
        raise ExecutionGatewayError(
            StructuredError(
                code="commit_tree_mismatch",
                message="promoted commit diff does not equal the validated candidate",
                path="workspace.commit",
                details={
                    "expected": sorted(expected),
                    "committed": sorted(committed),
                },
            )
        )
    for path, expected_hash in artifact_hashes.items():
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={workspace_root}", "show", f"{promoted_sha}:{path}"],
            cwd=str(workspace_root),
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise ExecutionGatewayError(
                StructuredError(
                    code="commit_tree_mismatch",
                    message=f"verified artifact is absent from commit: {path}",
                    path="workspace.commit",
                )
            )
        observed = f"sha256:{hashlib.sha256(completed.stdout).hexdigest()}"
        if observed != expected_hash:
            raise ExecutionGatewayError(
                StructuredError(
                    code="commit_tree_mismatch",
                    message=f"committed artifact hash diverges for {path}",
                    path="workspace.commit",
                    details={"expected": expected_hash, "observed": observed},
                )
            )


def promote_result(
    *,
    project_root: Path,
    ephemeral_root: Path,
    execution_id: str,
    promoted_sha: str,
) -> dict[str, Any]:
    """Mark ephemeral result as promotable/resumable after Core validation."""
    marker_path = ephemeral_meta_path(project_root, execution_id)
    marker: dict[str, Any] = {}
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = {}
    marker.update(
        {
            "promotable": True,
            "resumable": True,
            "promoted_sha": promoted_sha,
            "execution_id": execution_id,
            "worktree": str(ephemeral_root),
        }
    )
    atomic_write_text(marker_path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    registry = project_root / ".ai-team" / "supervisor" / "promotions" / f"{execution_id}.json"
    atomic_write_text(
        registry,
        json.dumps(
            {
                "execution_id": execution_id,
                "promoted_sha": promoted_sha,
                "ephemeral_path": str(ephemeral_root),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return marker


def quarantine_violation(
    *,
    project_root: Path,
    ephemeral_root: Path,
    execution_id: str,
    reason: str,
    files: list[str],
    last_healthy_sha: str,
) -> dict[str, Any]:
    """Quarantine a bounded diagnostic patch; never mark as resumable."""
    quarantine_dir = project_root / ".ai-team" / "supervisor" / "quarantine" / execution_id
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "execution_id": execution_id,
        "reason": reason,
        "files": files[:200],
        "last_healthy_sha": last_healthy_sha,
        "resumable": False,
        "promotable": False,
    }
    atomic_write_text(quarantine_dir / "violation.json", json.dumps(record, indent=2) + "\n")
    marker_path = ephemeral_meta_path(project_root, execution_id)
    branch: str | None = None
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = {}
        raw_branch = marker.get("branch")
        if isinstance(raw_branch, str) and raw_branch.startswith("ai-ephemeral/"):
            branch = raw_branch
        marker.update({"promotable": False, "resumable": False, "quarantined": True, "reason": reason})
        atomic_write_text(marker_path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    # Best-effort: remove ephemeral worktree so it cannot be selected for resume.
    try:
        _git(project_root, ["worktree", "remove", "--force", str(ephemeral_root)])
    except GitWorkspaceError:
        shutil.rmtree(ephemeral_root, ignore_errors=True)
    # Delete only the branch recorded in this execution's trusted marker.
    if branch is not None:
        try:
            _git(project_root, ["branch", "-D", "--", branch])
        except GitWorkspaceError:
            pass
    return record


def assert_epoch_fencing(*, request_epoch: int, result_epoch: int) -> None:
    try:
        left = int(request_epoch)
        right = int(result_epoch)
    except (TypeError, ValueError) as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message="epoch values are not integers",
                path="epoch",
            )
        ) from exc
    if left != right:
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message=f"result epoch {right} does not match request epoch {left}",
                path="epoch",
            )
        )


def assert_authoritative_lease(
    ai_team: Path,
    *,
    run_id: str,
    work_unit_id: str,
    lease_id: str,
    epoch: int,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Re-read authoritative lease/queue state before evidence, commit, or promotion."""
    run_path = ai_team / "runs" / f"{run_id}.yaml"
    lease_path = ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    if not lease_path.is_file():
        # Fall back to supervisor queue item when worker leases are not used.
        return _assert_queue_lease(
            ai_team,
            lease_id=lease_id,
            epoch=epoch,
            worker_id=worker_id,
        )
    try:
        lease = yaml.safe_load(lease_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message=f"authoritative lease unreadable: {exc}",
                path="lease_id",
            )
        ) from exc
    if not isinstance(lease, dict):
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message="authoritative lease is corrupt",
                path="lease_id",
            )
        )
    if lease.get("status") not in {None, "active"}:
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message=f"lease status {lease.get('status')!r} does not allow promotion",
                path="lease_id",
                details={"lease_id": lease_id, "status": lease.get("status")},
            )
        )
    observed_epoch = int(lease.get("epoch") or lease.get("lease_epoch") or 0)
    if observed_epoch and observed_epoch != int(epoch):
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message=(
                    f"authoritative lease epoch {observed_epoch} != request epoch {epoch}"
                ),
                path="epoch",
                details={"lease_id": lease_id, "authoritative_epoch": observed_epoch},
            )
        )
    if worker_id and lease.get("worker_id") not in (None, worker_id):
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message="lease is owned by a different worker",
                path="lease_id",
                details={"expected_worker": worker_id, "actual": lease.get("worker_id")},
            )
        )
    if run_path.is_file():
        try:
            run_document = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            run_document = {}
        current = (run_document.get("leases_by_work_unit") or {}).get(work_unit_id) or {}
        current_id = current.get("lease_id")
        current_epoch = current.get("epoch")
        if current_id and current_id != lease_id:
            raise ExecutionGatewayError(
                StructuredError(
                    code="stale_epoch",
                    message="run no longer references this lease_id for the Work Unit",
                    path="lease_id",
                    details={"current_lease_id": current_id, "claimed": lease_id},
                )
            )
        if current_epoch is not None and int(current_epoch) != int(epoch):
            raise ExecutionGatewayError(
                StructuredError(
                    code="stale_epoch",
                    message="run lease epoch no longer matches request",
                    path="epoch",
                    details={"current_epoch": current_epoch, "claimed": epoch},
                )
            )
    return lease


def _assert_queue_lease(
    ai_team: Path,
    *,
    lease_id: str,
    epoch: int,
    worker_id: str | None,
) -> dict[str, Any]:
    from governed_ai.core.supervisor import queue

    for item in queue.list_items(ai_team):
        if item.get("lease_id") != lease_id:
            continue
        if int(item.get("lease_epoch") or 0) != int(epoch):
            raise ExecutionGatewayError(
                StructuredError(
                    code="stale_epoch",
                    message="queue lease epoch no longer matches request",
                    path="epoch",
                    details={
                        "lease_id": lease_id,
                        "authoritative_epoch": item.get("lease_epoch"),
                        "claimed": epoch,
                    },
                )
            )
        if item.get("state") not in {"leased", "acknowledged"}:
            raise ExecutionGatewayError(
                StructuredError(
                    code="stale_epoch",
                    message=f"queue item state {item.get('state')!r} does not allow promotion",
                    path="lease_id",
                )
            )
        if worker_id and item.get("leased_by") not in (None, worker_id):
            raise ExecutionGatewayError(
                StructuredError(
                    code="stale_epoch",
                    message="queue lease owned by a different worker",
                    path="lease_id",
                )
            )
        return item
    # No authoritative lease document and no queue item: allow only when
    # callers explicitly operate without lease fencing (unit tests without runs).
    return {"lease_id": lease_id, "lease_epoch": epoch, "state": "untracked"}


def cas_promote_guard(
    ai_team: Path,
    *,
    execution_id: str,
    lease_id: str,
    epoch: int,
) -> Path:
    """Create an exclusive promotion claim so epoch cannot race the final write."""
    claims = ai_team / "supervisor" / "promotion-claims"
    claims.mkdir(parents=True, exist_ok=True)
    path = claims / f"{execution_id}.json"
    payload = {
        "execution_id": execution_id,
        "lease_id": lease_id,
        "epoch": epoch,
    }
    flags = __import__("os").O_CREAT | __import__("os").O_EXCL | __import__("os").O_WRONLY
    try:
        fd = __import__("os").open(str(path), flags)
    except FileExistsError as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="stale_epoch",
                message="promotion claim already held (concurrent or stale worker)",
                path="execution_id",
                details={"execution_id": execution_id},
            )
        ) from exc
    with __import__("os").fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True))
        handle.flush()
        __import__("os").fsync(handle.fileno())
    return path
