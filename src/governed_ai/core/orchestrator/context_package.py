"""Context Package completeness checks for dispatch gating."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def derive_required_contracts(
    workspace_root: Path, wu_document: dict[str, Any]
) -> list[str]:
    """Derive shared-contract paths referenced by the Work Unit.

    Looks under ``contracts/`` (project) and ``.ai-team/contracts/`` for files
    whose stem or relative path appears in WU ``dependencies`` entries that look
    like contract refs (contain ``/`` or end with ``.json``/``.yaml``). Plain WU
    dependency ids are ignored.
    """
    required: list[str] = []
    roots = [
        workspace_root / "contracts",
        workspace_root / ".ai-team" / "contracts",
    ]
    for dep in wu_document.get("dependencies") or []:
        text = str(dep).strip().replace("\\", "/")
        if not text:
            continue
        if "/" not in text and not text.endswith((".json", ".yaml", ".yml")):
            continue
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = workspace_root / text
        if candidate.is_file():
            try:
                required.append(candidate.relative_to(workspace_root).as_posix())
            except ValueError:
                required.append(text)
            continue
        for root in roots:
            alt = root / text
            if alt.is_file():
                try:
                    required.append(alt.relative_to(workspace_root).as_posix())
                except ValueError:
                    required.append(alt.as_posix())
                break
        else:
            required.append(text)
    # stable unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in required:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def evaluate_context_package_completeness(
    *,
    workspace_root: Path,
    context_document: dict[str, Any],
    context_path: Path,
    wu_document: dict[str, Any],
) -> dict[str, Any]:
    """Return completeness fields; does not mutate the on-disk package."""
    required = list(context_document.get("required_contracts") or [])
    if not required:
        required = derive_required_contracts(workspace_root, wu_document)

    item_sources = {
        str(item.get("source")).replace("\\", "/")
        for item in (context_document.get("items") or [])
        if isinstance(item, dict) and item.get("source")
    }
    missing: list[str] = []
    for contract in required:
        rel = str(contract).replace("\\", "/")
        path = workspace_root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        if rel not in item_sources and path.name not in {
            Path(src).name for src in item_sources
        }:
            missing.append(rel)

    open_requests = [
        req
        for req in (context_document.get("open_context_requests") or [])
        if req
    ]
    if open_requests:
        for req in open_requests:
            label = (
                req.get("id")
                if isinstance(req, dict)
                else str(req)
            )
            missing.append(f"open_context_request:{label}")

    source_sha = None
    if context_path.is_file():
        try:
            source_sha = _sha256_file(context_path)
        except OSError:
            source_sha = None

    status = "complete" if not missing else "incomplete"
    return {
        "source_sha256": source_sha,
        "required_contracts": required,
        "completeness_status": status,
        "missing_inputs": missing,
    }


def completeness_error(evaluation: dict[str, Any]) -> str | None:
    if evaluation.get("completeness_status") == "complete":
        return None
    missing = evaluation.get("missing_inputs") or []
    joined = ", ".join(str(item) for item in missing[:5])
    more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
    return f"context_package incomplete: {joined}{more}"
