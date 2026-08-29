"""WU-P2-PARITY-TEST — semantic parity bundle ↔ Cursor agents/skills (Document 13 §5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.contracts.semantic_parity import (
    check_semantic_parity,
    format_divergence_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"


def test_semantic_parity_bundle_matches_cursor_artefacts() -> None:
    """L1 contract test — bundle roles/procedures align with .cursor agents/skills."""
    divergences = check_semantic_parity(REPO_ROOT, BUNDLE_V1)
    if divergences:
        pytest.fail(format_divergence_report(divergences))


def test_semantic_parity_report_includes_identifiers_on_fixture_drift(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    roles_dir = bundle / "roles"
    procedures_dir = bundle / "procedures"
    roles_dir.mkdir(parents=True)
    procedures_dir.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps({"roles": [], "procedures": []}),
        encoding="utf-8",
    )
    (roles_dir / "backend-developer.json").write_text(
        json.dumps(
            {
                "role_id": "backend-developer",
                "revision": "1.0.0",
                "mandate": "Implement approved backend Work Units within scope.",
                "writes": {
                    "product": {"level": "scoped", "paths": []},
                    "authoritative_governance_commands": [],
                    "non_authoritative_signal_commands": [],
                },
                "capabilities": {
                    "repository_read": True,
                    "shell": "scoped",
                    "network": "deny",
                    "external_tools": [],
                },
                "approval_policy": {"mode": "constitution", "cannot_relax": True},
                "procedure_refs": [{"procedure_id": "implement-work-unit", "revision": "1.0.0"}],
                "model_preference": "inherit",
                "isolation": "not_required",
            }
        ),
        encoding="utf-8",
    )
    (procedures_dir / "orchestrator.json").write_text(
        json.dumps(
            {
                "procedure_id": "orchestrator",
                "revision": "1.0.0",
                "intent": "Coordinate Work Units without product authority.",
                "invocation_mode": "explicit_only",
                "required_inputs": [],
                "steps": ["Determine READY Work Units"],
                "required_outputs": [],
                "invariants": ["Do not bypass human gates"],
            }
        ),
        encoding="utf-8",
    )

    cursor = tmp_path / "cursor_root"
    (cursor / ".cursor" / "agents").mkdir(parents=True)
    (cursor / ".cursor" / "skills").mkdir(parents=True)

    divergences = check_semantic_parity(cursor, bundle)
    identifiers = {d.identifier for d in divergences}
    kinds = {d.kind for d in divergences}
    assert "backend-developer" in identifiers
    assert "orchestrator" in identifiers
    assert "role" in kinds
    assert "procedure" in kinds
    report = format_divergence_report(divergences)
    assert "backend-developer" in report
    assert "orchestrator" in report
