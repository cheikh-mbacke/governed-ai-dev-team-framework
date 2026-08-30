"""JSON Schema artefacts for protocol and published bundle (Document 12 §2).

Namespaced extensions use root property names matching
``^x-[a-z0-9]+(-[a-z0-9]+)+$`` (example: ``x-vendor-meta``). All other
undeclared properties are rejected (``additionalProperties: false``).
"""

from __future__ import annotations

from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parent

BUNDLE_MANIFEST_SCHEMA = SCHEMAS_DIR / "bundle-manifest.schema.json"
ROLE_DEFINITION_REVISION_SCHEMA = SCHEMAS_DIR / "role-definition-revision.schema.json"
PROCEDURE_REVISION_SCHEMA = SCHEMAS_DIR / "procedure-revision.schema.json"

__all__ = [
    "BUNDLE_MANIFEST_SCHEMA",
    "PROCEDURE_REVISION_SCHEMA",
    "ROLE_DEFINITION_REVISION_SCHEMA",
    "SCHEMAS_DIR",
]
