"""Compile a Published Contract Bundle into staged Cursor artefacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import render_agent_from_role
from .staging import (
    artifact_kind,
    sha256_bytes,
    validate_pre_install,
)
from governed_ai.contracts.validate_bundle import validate_bundle

ADAPTER_ID = "cursor"
ADAPTER_VERSION = "0.5.0"
CURSOR_SUBDIR = ".cursor"
BUNDLE_ROLE_AGENT = {
    "architect",
    "auditor",
    "backend-developer",
    "code-reviewer",
    "frontend-developer",
    "product-analyst",
    "qa-test",
    "release-agent",
    "security-reviewer",
    "requirements-challenger",
    "mandate-matcher",
    "test-strategist",
    "integration-steward",
}


def _default_templates_root() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"


def _load_roles(bundle_dir: Path) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    roles_dir = bundle_dir / "roles"
    for path in sorted(roles_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        roles[str(doc["role_id"])] = doc
    return roles


def _transform_file(
    rel_posix: str,
    content: bytes,
    roles: dict[str, dict[str, Any]],
) -> bytes:
    if not rel_posix.startswith(f"{CURSOR_SUBDIR}/agents/") or not rel_posix.endswith(".md"):
        return content

    agent_id = Path(rel_posix).stem
    if agent_id not in BUNDLE_ROLE_AGENT:
        return content

    role = roles.get(agent_id)
    if role is None:
        return content

    text = content.decode("utf-8")
    rendered = render_agent_from_role(text, role)
    return rendered.encode("utf-8")


def compile_manifest(
    bundle_dir: Path,
    staging_dir: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    templates_root: Path | None = None,
) -> dict[str, Any]:
    """Validate bundle, write staged ``.cursor/`` tree, return Artifact Manifest."""
    _ = project_profile  # reserved for profile-driven allowlist diffs (later WU)

    bundle_dir = bundle_dir.resolve()
    staging_dir = staging_dir.resolve()
    templates_root = (templates_root or _default_templates_root()).resolve()
    template_cursor = templates_root / CURSOR_SUBDIR
    if not template_cursor.is_dir():
        raise FileNotFoundError(f"cursor templates missing: {template_cursor}")

    validation = validate_bundle(bundle_dir)
    if not validation.accepted:
        issues = "; ".join(f"{i.code}: {i.message}" for i in validation.issues)
        raise ValueError(f"bundle validation failed: {issues}")

    bundle_manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    bundle_version = str(bundle_manifest["bundle_version"])
    roles = _load_roles(bundle_dir)

    if staging_dir.exists():
        for path in sorted(staging_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    staging_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, str]] = []
    for src_path in sorted(template_cursor.rglob("*")):
        if not src_path.is_file():
            continue

        rel_under_cursor = src_path.relative_to(template_cursor).as_posix()
        rel_posix = f"{CURSOR_SUBDIR}/{rel_under_cursor}"
        content = src_path.read_bytes()
        content = _transform_file(rel_posix, content, roles)

        dst_path = staging_dir / rel_posix
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(content)

        artifacts.append(
            {
                "kind": artifact_kind(rel_posix),
                "path": rel_posix,
                "sha256": sha256_bytes(content),
            }
        )

    artifacts.sort(key=lambda entry: entry["path"])
    manifest: dict[str, Any] = {
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "bundle_version": bundle_version,
        "artifacts": artifacts,
    }
    validate_pre_install(staging_dir, manifest)
    return manifest


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "compile_manifest"]
