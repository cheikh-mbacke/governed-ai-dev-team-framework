"""Helpers to build minimal Published Contract Bundle fixtures for CT tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from governed_ai.contracts.bundle_hash import compute_bundle_content_hash

MINIMAL_PROCEDURE: dict[str, Any] = {
    "procedure_id": "implement-work-unit",
    "revision": "1.0.0",
    "intent": "Implement the approved Work Unit and return a verifiable handoff.",
    "invocation_mode": "explicit_only",
    "required_inputs": ["work_unit", "context_package", "base_sha"],
    "steps": ["Read inputs", "Implement within scope", "Run required checks"],
    "required_outputs": ["result_sha", "checks", "limitations"],
    "invariants": ["Do not change product authority", "Do not broaden scope"],
}

MINIMAL_ROLE: dict[str, Any] = {
    "role_id": "backend-developer",
    "revision": "1.0.0",
    "mandate": "Implement approved backend Work Units within scope.",
    "writes": {
        "product": {"level": "scoped", "paths": ["<work-unit-scope>"]},
        "authoritative_governance_commands": [],
        "non_authoritative_signal_commands": ["RecordObservation"],
    },
    "capabilities": {
        "repository_read": True,
        "shell": "scoped",
        "network": "deny_by_default",
        "external_tools": [],
    },
    "approval_policy": {"mode": "constitution", "cannot_relax": True},
    "procedure_refs": [{"procedure_id": "implement-work-unit", "revision": "1.0.0"}],
    "model_preference": "inherit",
    "isolation": "required_for_concurrent_product_write",
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_minimal_bundle(
    bundle_dir: Path,
    *,
    role: dict[str, Any] | None = None,
    procedure: dict[str, Any] | None = None,
    extra_roles: list[tuple[str, dict[str, Any]]] | None = None,
    extra_procedures: list[tuple[str, dict[str, Any]]] | None = None,
    manifest_extras: dict[str, Any] | None = None,
    role_rel: str = "roles/backend-developer.json",
    procedure_rel: str = "procedures/implement-work-unit.json",
) -> Path:
    """Write a minimal valid-shaped bundle and seal content_hash. Returns bundle_dir."""
    role_doc = copy.deepcopy(role if role is not None else MINIMAL_ROLE)
    proc_doc = copy.deepcopy(procedure if procedure is not None else MINIMAL_PROCEDURE)

    write_json(bundle_dir / role_rel, role_doc)
    write_json(bundle_dir / procedure_rel, proc_doc)

    role_paths = [role_rel]
    proc_paths = [procedure_rel]

    for rel, doc in extra_roles or []:
        write_json(bundle_dir / rel, doc)
        role_paths.append(rel)
    for rel, doc in extra_procedures or []:
        write_json(bundle_dir / rel, doc)
        proc_paths.append(rel)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "bundle_version": "1.0.0",
        "created_at": "2026-08-28T10:00:00Z",
        "content_hash": "sha256:" + ("0" * 64),
        "roles": role_paths,
        "procedures": proc_paths,
    }
    if manifest_extras:
        manifest.update(manifest_extras)

    digest = compute_bundle_content_hash(bundle_dir, manifest)
    manifest["content_hash"] = digest
    write_json(bundle_dir / "manifest.json", manifest)
    return bundle_dir
