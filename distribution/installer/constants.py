"""Shared Distribution installer constants."""

from __future__ import annotations

from pathlib import Path

from distribution.installer.version_policy import SUPPORTED_UPDATE_FROM

# Installed-target copy map (Document 11 §4). Framework repo layout unchanged.
COPY_ITEMS = [
    ".cursor",
    ".ai-team",
    "scripts",
    "AGENTS.md",
    "src/governed_ai",
    "adapters/cursor",
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
    ".ai-team/reconciliation/*",
    ".ai-team/runs/*",
    ".ai-team/runs/leases/*",
    ".ai-team/runs/execution-attempts/*",
    ".ai-team/runs/checkpoints/*",
    ".ai-team/runs/decisions/*",
    ".ai-team/runs/integration-merges/*",
    ".ai-team/runs/escalations/*",
    ".ai-team/run-authorization-grants/*",
    ".ai-team/mission-artifacts/*",
    ".ai-team/migration-backups/*",
    ".ai-team/project-profile.yaml.bak",
]

FRESH_PROJECT_SEEDS = (
    ".ai-team/project-profile.yaml",
    ".ai-team/state/project-state.yaml",
    ".ai-team/sources/source-registry.yaml",
)

LEGACY_VERSION_REL = Path(".ai-team/framework-version.json")
FABRIC_SOURCE_VERSION_REL = Path(".fabric/framework-version.json")

# Marker files indicating a prior framework installation (not collisions on fresh install).
FRAMEWORK_INSTALL_MARKERS = frozenset(
    {
        ".ai-team/installation-record.json",
        ".ai-team/framework-version.json",
        ".ai-team/project-profile.yaml",
        ".ai-team/state/project-state.yaml",
    }
)

__all__ = [
    "COPY_ITEMS",
    "FRESH_PROJECT_SEEDS",
    "FRAMEWORK_INSTALL_MARKERS",
    "LEGACY_VERSION_REL",
    "PROJECT_OWNED_PATTERNS",
    "SUPPORTED_UPDATE_FROM",
]
