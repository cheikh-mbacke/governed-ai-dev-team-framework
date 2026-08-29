"""Publish an accepted Contract Bundle into an immutable versioned tree.

Document 11 §4 layout::

    <contracts_root>/
      active-bundle.json
      bundles/<bundle_version>/...

Only files listed in the manifest (``manifest.json`` plus ``roles`` /
``procedures`` paths) are copied. Adapter sidecars such as
``cursor-compiler-notes.yaml`` stay in the source tree and are never published.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.contracts.bundle_hash import compute_bundle_content_hash
from governed_ai.contracts.validate_bundle import (
    MANIFEST_NAME,
    BundleValidationResult,
    ValidationIssue,
    validate_bundle,
)

ACTIVE_BUNDLE_NAME = "active-bundle.json"
BUNDLES_DIR_NAME = "bundles"


class BundlePublishError(Exception):
    """Raised when publication is refused (validation or immutability)."""

    def __init__(self, message: str, *, issues: list[ValidationIssue] | None = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


@dataclass(frozen=True)
class PublishResult:
    """Outcome of a successful (or idempotent) publication."""

    bundle_version: str
    content_hash: str
    published_dir: Path
    active_pointer_path: Path
    active_pointer: dict[str, str]
    idempotent: bool = False


def _read_manifest(source_dir: Path) -> dict[str, Any]:
    path = source_dir / MANIFEST_NAME
    if not path.is_file():
        raise BundlePublishError(f"missing {MANIFEST_NAME}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundlePublishError(f"cannot read {MANIFEST_NAME}: {exc}") from exc
    if not isinstance(data, dict):
        raise BundlePublishError("manifest root must be an object")
    return data


def _published_paths(manifest: dict[str, Any]) -> list[str]:
    """Relative paths that belong in the published tree (manifest + refs)."""
    paths = [MANIFEST_NAME]
    for rel in list(manifest.get("roles") or []):
        if isinstance(rel, str):
            paths.append(rel)
    for rel in list(manifest.get("procedures") or []):
        if isinstance(rel, str):
            paths.append(rel)
    return paths


def _copy_published_files(source_dir: Path, dest_dir: Path, manifest: dict[str, Any]) -> None:
    root = source_dir.resolve()
    dest = dest_dir.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    for rel in _published_paths(manifest):
        src = (root / rel).resolve()
        if not src.is_relative_to(root):
            raise BundlePublishError(f"referenced path escapes source root: {rel}")
        if not src.is_file():
            raise BundlePublishError(f"referenced file missing: {rel}")
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)


def _write_active_pointer(
    target_root: Path,
    *,
    bundle_version: str,
    content_hash: str,
) -> tuple[Path, dict[str, str]]:
    pointer = {
        "bundle_version": bundle_version,
        "path": f"{BUNDLES_DIR_NAME}/{bundle_version}",
        "content_hash": content_hash,
    }
    path = target_root / ACTIVE_BUNDLE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pointer, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path, pointer


def _existing_published_hash(published_dir: Path) -> str | None:
    if not published_dir.is_dir():
        return None
    manifest_path = published_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    declared = manifest.get("content_hash")
    if isinstance(declared, str) and declared.startswith("sha256:"):
        try:
            return compute_bundle_content_hash(published_dir, manifest)
        except (OSError, ValueError):
            return declared
    return None


def publish_bundle(source_dir: Path, target_root: Path) -> PublishResult:
    """Validate ``source_dir`` and publish into ``target_root/bundles/<version>/``.

    Parameters
    ----------
    source_dir:
        Directory containing ``manifest.json`` and referenced role/procedure files.
    target_root:
        Contracts root (e.g. ``.ai-team/contracts``). Receives ``bundles/`` and
        ``active-bundle.json``.

    Raises
    ------
    BundlePublishError
        When validation fails, a cross-ref is missing, or an existing published
        directory has a different content hash (immutability).
    """
    source = source_dir.resolve()
    root = target_root.resolve()

    validation: BundleValidationResult = validate_bundle(source)
    if not validation.accepted:
        raise BundlePublishError(
            "source bundle validation rejected",
            issues=validation.issues,
        )

    manifest = validation.manifest or _read_manifest(source)
    bundle_version = manifest.get("bundle_version")
    if not isinstance(bundle_version, str) or not bundle_version:
        raise BundlePublishError("manifest missing bundle_version")

    content_hash = validation.content_hash
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
        raise BundlePublishError("validated bundle missing content_hash")

    # Cross-refs already enforced by validate_bundle; assert for handoff clarity.
    for role_id, role_doc in validation.roles.items():
        refs = role_doc.get("procedure_refs") or []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            proc_id = ref.get("procedure_id")
            if isinstance(proc_id, str) and proc_id not in validation.procedures:
                raise BundlePublishError(
                    f"role {role_id!r} references missing procedure {proc_id!r}",
                    issues=[
                        ValidationIssue(
                            code="INVARIANT_VIOLATION",
                            message=f"missing referenced procedure: {proc_id}",
                            path=f"role:{role_id}",
                        )
                    ],
                )

    published_dir = root / BUNDLES_DIR_NAME / bundle_version

    if published_dir.exists():
        existing_hash = _existing_published_hash(published_dir)
        if existing_hash == content_hash:
            pointer_path, pointer = _write_active_pointer(
                root,
                bundle_version=bundle_version,
                content_hash=content_hash,
            )
            return PublishResult(
                bundle_version=bundle_version,
                content_hash=content_hash,
                published_dir=published_dir,
                active_pointer_path=pointer_path,
                active_pointer=pointer,
                idempotent=True,
            )
        raise BundlePublishError(
            f"refusing to overwrite published bundle {bundle_version!r}: "
            f"existing hash {existing_hash!r} != source hash {content_hash!r}",
            issues=[
                ValidationIssue(
                    code="INVARIANT_VIOLATION",
                    message="published bundle is immutable; content differs",
                    path=str(published_dir.as_posix()),
                )
            ],
        )

    staging = root / BUNDLES_DIR_NAME / f".staging-{bundle_version}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _copy_published_files(source, staging, manifest)
        # Confirm published tree still validates and hash matches.
        staged_result = validate_bundle(staging)
        if not staged_result.accepted or staged_result.content_hash != content_hash:
            raise BundlePublishError(
                "staged published tree failed validation or hash mismatch",
                issues=staged_result.issues,
            )
        staging.rename(published_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    pointer_path, pointer = _write_active_pointer(
        root,
        bundle_version=bundle_version,
        content_hash=content_hash,
    )
    return PublishResult(
        bundle_version=bundle_version,
        content_hash=content_hash,
        published_dir=published_dir,
        active_pointer_path=pointer_path,
        active_pointer=pointer,
        idempotent=False,
    )


__all__ = [
    "ACTIVE_BUNDLE_NAME",
    "BUNDLES_DIR_NAME",
    "BundlePublishError",
    "PublishResult",
    "publish_bundle",
]
