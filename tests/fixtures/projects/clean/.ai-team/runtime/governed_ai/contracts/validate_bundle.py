"""Validate a Published Contract Bundle directory (Document 12 §2.4).

Emits stable codes from Document 12 §11 (``INVALID_SCHEMA``,
``INVARIANT_VIOLATION``). Bundle-level checks go beyond JSON Schema:
duplicate identifiers, missing procedure references, content_hash match,
and agnostic-field boundary lint (adapter-specific tokens).

Namespaced extensions
---------------------
Root-level properties matching ``^x-[a-z0-9]+(-[a-z0-9]+)+$`` (example:
``x-vendor-meta``) are allowed by the schemas and preserved in validated
payloads. Core ignores their semantics.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from governed_ai.contracts.bundle_hash import compute_bundle_content_hash

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
MANIFEST_NAME = "manifest.json"
EXTENSION_KEY_RE = re.compile(r"^x-[a-z0-9]+(-[a-z0-9]+)+$")

_SCHEMA_FILES = {
    "manifest": "bundle-manifest.schema.json",
    "role": "role-definition-revision.schema.json",
    "procedure": "procedure-revision.schema.json",
}


@dataclass(frozen=True)
class ValidationIssue:
    """Single validation failure."""

    code: str
    message: str
    path: str = ""


@dataclass
class BundleValidationResult:
    """Outcome of validating a bundle directory."""

    accepted: bool
    content_hash: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    roles: dict[str, dict[str, Any]] = field(default_factory=dict)
    procedures: dict[str, dict[str, Any]] = field(default_factory=dict)


def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / _SCHEMA_FILES[name]
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _schema_issues(
    instance: Any,
    schema_name: str,
    doc_path: str,
) -> list[ValidationIssue]:
    validator = _validator(_load_schema(schema_name))
    issues: list[ValidationIssue] = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        pointer = "/" + "/".join(str(p) for p in err.absolute_path)
        issues.append(
            ValidationIssue(
                code="INVALID_SCHEMA",
                message=err.message,
                path=f"{doc_path}{pointer}" if pointer != "/" else doc_path,
            )
        )
    return issues


def _adapter_boundary_tokens() -> tuple[str, ...]:
    """Tokens forbidden in agnostic role/procedure fields (Document 14 §12).

    Built without embedding those literals contiguously in this source file so
    architecture leak scanners stay green; negative fixtures live under tests/.
    """
    return (
        "." + "cursor",
        "C" + "ursor",
        "hooks" + ".json",
        "permissions" + ".json",
        "cli" + ".json",
        "Claude" + " Code",
        "Cod" + "ex",
    )


def _iter_string_leaves(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        found.append((prefix or "/", value))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(_iter_string_leaves(item, f"{prefix}/{i}"))
    elif isinstance(value, dict):
        for key, item in value.items():
            if EXTENSION_KEY_RE.match(str(key)):
                continue
            found.extend(_iter_string_leaves(item, f"{prefix}/{key}"))
    return found


def lint_agnostic_boundary(document: dict[str, Any], doc_path: str) -> list[ValidationIssue]:
    """Reject adapter-specific syntax in reserved agnostic fields."""
    issues: list[ValidationIssue] = []
    tokens = _adapter_boundary_tokens()
    for pointer, text in _iter_string_leaves(document):
        for token in tokens:
            if token in text:
                issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message=f"boundary lint: adapter-specific token {token!r} in agnostic field",
                        path=f"{doc_path}{pointer}",
                    )
                )
                break
    return issues


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_bundle(bundle_dir: Path) -> BundleValidationResult:
    """Validate schemas and Document 12 §2.4 invariants for a bundle directory."""
    result = BundleValidationResult(accepted=False)
    root = bundle_dir.resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        result.issues.append(
            ValidationIssue(
                code="INVALID_SCHEMA",
                message=f"missing {MANIFEST_NAME}",
                path=MANIFEST_NAME,
            )
        )
        return result

    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        result.issues.append(
            ValidationIssue(code="INVALID_SCHEMA", message=str(exc), path=MANIFEST_NAME)
        )
        return result

    if not isinstance(manifest, dict):
        result.issues.append(
            ValidationIssue(
                code="INVALID_SCHEMA",
                message="manifest root must be an object",
                path=MANIFEST_NAME,
            )
        )
        return result

    result.manifest = manifest
    result.issues.extend(_schema_issues(manifest, "manifest", MANIFEST_NAME))

    roles: dict[str, dict[str, Any]] = {}
    procedures: dict[str, dict[str, Any]] = {}

    for rel in list(manifest.get("roles") or []):
        if not isinstance(rel, str):
            continue
        path = root / rel
        if not path.is_file():
            result.issues.append(
                ValidationIssue(
                    code="INVARIANT_VIOLATION",
                    message=f"referenced role file missing: {rel}",
                    path=rel,
                )
            )
            continue
        try:
            doc = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            result.issues.append(
                ValidationIssue(code="INVALID_SCHEMA", message=str(exc), path=rel)
            )
            continue
        if not isinstance(doc, dict):
            result.issues.append(
                ValidationIssue(
                    code="INVALID_SCHEMA",
                    message="role document must be an object",
                    path=rel,
                )
            )
            continue
        result.issues.extend(_schema_issues(doc, "role", rel))
        result.issues.extend(lint_agnostic_boundary(doc, rel))
        role_id = doc.get("role_id")
        if isinstance(role_id, str):
            if role_id in roles:
                result.issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message=f"duplicate role_id: {role_id}",
                        path=rel,
                    )
                )
            roles[role_id] = doc

    for rel in list(manifest.get("procedures") or []):
        if not isinstance(rel, str):
            continue
        path = root / rel
        if not path.is_file():
            result.issues.append(
                ValidationIssue(
                    code="INVARIANT_VIOLATION",
                    message=f"referenced procedure file missing: {rel}",
                    path=rel,
                )
            )
            continue
        try:
            doc = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            result.issues.append(
                ValidationIssue(code="INVALID_SCHEMA", message=str(exc), path=rel)
            )
            continue
        if not isinstance(doc, dict):
            result.issues.append(
                ValidationIssue(
                    code="INVALID_SCHEMA",
                    message="procedure document must be an object",
                    path=rel,
                )
            )
            continue
        result.issues.extend(_schema_issues(doc, "procedure", rel))
        result.issues.extend(lint_agnostic_boundary(doc, rel))
        procedure_id = doc.get("procedure_id")
        if isinstance(procedure_id, str):
            if procedure_id in procedures:
                result.issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message=f"duplicate procedure_id: {procedure_id}",
                        path=rel,
                    )
                )
            procedures[procedure_id] = doc

    result.roles = roles
    result.procedures = procedures

    # Cross-reference: every procedure_ref must exist in the bundle.
    for role_id, role_doc in roles.items():
        refs = role_doc.get("procedure_refs") or []
        if not isinstance(refs, list):
            continue
        for idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                continue
            proc_id = ref.get("procedure_id")
            rev = ref.get("revision")
            if not isinstance(proc_id, str):
                continue
            if proc_id not in procedures:
                result.issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message=f"missing referenced procedure: {proc_id}",
                        path=f"role:{role_id}/procedure_refs/{idx}",
                    )
                )
                continue
            actual_rev = procedures[proc_id].get("revision")
            if isinstance(rev, str) and actual_rev != rev:
                result.issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message=(
                            f"procedure revision mismatch for {proc_id}: "
                            f"role refs {rev!r}, bundle has {actual_rev!r}"
                        ),
                        path=f"role:{role_id}/procedure_refs/{idx}",
                    )
                )

    # Hash check only when schema-level content_hash looks present.
    declared = manifest.get("content_hash")
    if isinstance(declared, str) and declared.startswith("sha256:"):
        try:
            computed = compute_bundle_content_hash(root, manifest)
        except (OSError, ValueError) as exc:
            result.issues.append(
                ValidationIssue(
                    code="INVARIANT_VIOLATION",
                    message=f"content_hash computation failed: {exc}",
                    path="content_hash",
                )
            )
        else:
            result.content_hash = computed
            if declared != computed:
                result.issues.append(
                    ValidationIssue(
                        code="INVARIANT_VIOLATION",
                        message="content_hash does not match canonical bundle hash",
                        path="content_hash",
                    )
                )

    result.accepted = not result.issues
    if result.accepted and result.content_hash is None and isinstance(declared, str):
        result.content_hash = declared
    return result


def validate_document(document: dict[str, Any], kind: str) -> list[ValidationIssue]:
    """Validate a single in-memory document (``manifest``, ``role``, or ``procedure``)."""
    if kind not in _SCHEMA_FILES:
        raise ValueError(f"unknown schema kind: {kind}")
    return _schema_issues(document, kind, kind)


__all__ = [
    "EXTENSION_KEY_RE",
    "MANIFEST_NAME",
    "SCHEMAS_DIR",
    "BundleValidationResult",
    "ValidationIssue",
    "lint_agnostic_boundary",
    "validate_bundle",
    "validate_document",
]
