"""Canonical enums and constants for Design Authority."""

from __future__ import annotations

from typing import Literal

SCHEMA_VERSION = 1

DesignMode = Literal["conform", "adapt", "create", "maintain", "explore"]
AuthorityLevel = Literal["authoritative", "advisory", "inspiration_only", "deprecated"]
ArtifactStatus = Literal["active", "superseded", "withdrawn", "draft"]
SourceType = Literal[
    "png",
    "jpg",
    "jpeg",
    "webp",
    "svg",
    "pdf",
    "html_static",
    "figma_link",
    "screenshot",
    "wireframe",
    "tokens_json",
    "markdown_spec",
    "other",
]
InformationOrigin = Literal[
    "explicitly_provided",
    "human_decision",
    "extracted_from_artifact",
    "inherited_design_system",
    "compiler_default",
    "inference_proposed",
    "inference_validated",
]
ConformanceLevel = Literal[
    "exact",
    "tolerant_visual",
    "structural",
    "behavioral",
    "advisory",
]
DivergenceKind = Literal[
    "defect",
    "allowed_adaptation",
    "environment_variance",
    "reference_ambiguity",
    "design_system_conflict",
    "product_decision_required",
    "reference_outdated",
]
DivergenceSeverity = Literal["blocking", "major", "minor", "advisory"]

DESIGN_MODES: frozenset[str] = frozenset(
    {"conform", "adapt", "create", "maintain", "explore"}
)
AUTHORITY_LEVELS: frozenset[str] = frozenset(
    {"authoritative", "advisory", "inspiration_only", "deprecated"}
)
INFORMATION_ORIGINS: frozenset[str] = frozenset(
    {
        "explicitly_provided",
        "human_decision",
        "extracted_from_artifact",
        "inherited_design_system",
        "compiler_default",
        "inference_proposed",
        "inference_validated",
    }
)
CREATIVE_PROCEDURES: frozenset[str] = frozenset(
    {"create-frontend-design", "frontend-design"}
)
MODE_TO_PROCEDURE: dict[str, str] = {
    "conform": "implement-approved-design",
    "adapt": "adapt-approved-design",
    "create": "create-frontend-design",
    "maintain": "design-system-integration",
    "explore": "create-frontend-design",
}

SUPPORTED_LOCAL_EXTENSIONS: dict[str, str] = {
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".webp": "webp",
    ".svg": "svg",
    ".pdf": "pdf",
    ".html": "html_static",
    ".htm": "html_static",
    ".json": "tokens_json",
    ".md": "markdown_spec",
    ".markdown": "markdown_spec",
}

MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
MAX_REMOTE_URL_LENGTH = 2048

APPROVED_REMOTE_SCHEMES = frozenset({"https"})
FIGMA_HOST_SUFFIXES = (".figma.com", "figma.com")
