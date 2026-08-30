"""Shared Distribution installer constants."""

from __future__ import annotations

from pathlib import Path

COPY_ITEMS = [
    ".cursor",
    ".ai-team",
    "adapters/cursor",
    "src",
    "scripts",
    "docs/product",
    "docs/operator",
    "README.md",
    "AGENTS.md",
    "requirements.txt",
]

PROJECT_OWNED_PATTERNS = [
    ".ai-team/project-profile.yaml",
    ".ai-team/sources/source-registry.yaml",
    ".ai-team/work-units/*",
    ".ai-team/state/*",
    ".ai-team/decisions/*",
    ".ai-team/events/*",
    ".ai-team/evidence/*",
    ".ai-team/findings/*",
    ".ai-team/audits/*",
    ".ai-team/releases/*",
    ".ai-team/acceptance/*",
    ".ai-team/authorizations/*",
    ".ai-team/context-packages/*",
    ".ai-team/logs/*",
    ".ai-team/metrics/*",
    ".ai-team/observations/*",
    ".ai-team/retrospectives/*",
    ".ai-team/migration-backups/*",
    ".ai-team/project-profile.yaml.bak",
]

FRESH_PROJECT_SEEDS = (
    ".ai-team/project-profile.yaml",
    ".ai-team/state/project-state.yaml",
    ".ai-team/sources/source-registry.yaml",
)

SUPPORTED_UPDATE_FROM = {None, "0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0"}

LEGACY_VERSION_REL = Path(".ai-team/framework-version.json")