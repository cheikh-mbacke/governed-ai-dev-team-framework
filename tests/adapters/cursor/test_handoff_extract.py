"""Governed handoff extraction — prose-tolerant, contract-strict."""

from __future__ import annotations

import json

from adapters.cursor.runtime.results import extract_governed_handoff

_VALID_HANDOFF = {
    "summary": "WU-INV-01 delivered on synthetic SHA",
    "checks": [
        {
            "name": "AC-INV-01-01",
            "status": "passed",
            "evidence_ref": ".ai-team/evidence/WU-INV-01/ac-01.md",
        },
        {
            "name": "AC-INV-01-02",
            "status": "passed",
            "evidence_ref": ".ai-team/evidence/WU-INV-01/ac-02.md",
        },
    ],
    "artifacts": [
        {
            "kind": "code",
            "path": "services/investment/pom.xml",
            "sha256": "sha256:" + "a" * 64,
        }
    ],
    "requested_commands": [],
    "usage": {},
}


def test_extract_exact_json_handoff() -> None:
    handoff, error = extract_governed_handoff(json.dumps(_VALID_HANDOFF))
    assert error is None
    assert handoff is not None
    assert handoff["summary"].startswith("WU-INV-01")
    assert handoff["checks"][0]["name"] == "AC-INV-01-01"


def test_extract_fenced_json_handoff() -> None:
    text = (
        "Done.\n```json\n"
        + json.dumps(_VALID_HANDOFF, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    handoff, error = extract_governed_handoff(text)
    assert error is None
    assert handoff is not None
    assert len(handoff["checks"]) == 2


def test_extract_prose_then_json_regression_from_real_run() -> None:
    """Regression: agent progress prose before a valid handoff object.

    Shape observed on sads-ecosystem-backend (2026-09-10/11): checks were empty
    because ``json.loads`` required the whole result text to be exact JSON.
    """
    text = (
        "I'll implement WU-INV-01 within the declared scope: first read the "
        "project profile, work unit, and existing service template.\n"
        "There's already an investment tree — I'll compare it to the template.\n"
        "Implementation is already present — verifying acceptance criteria next.\n"
        + json.dumps(_VALID_HANDOFF, ensure_ascii=False, indent=2)
    )
    handoff, error = extract_governed_handoff(text)
    assert error is None
    assert handoff is not None
    assert handoff["checks"][0]["name"] == "AC-INV-01-01"
    assert handoff["artifacts"][0]["path"].endswith("pom.xml")


def test_extract_truncated_json_fails() -> None:
    text = '{"summary": "incomplete", "checks": [{"name": "AC-1"'
    handoff, error = extract_governed_handoff(text)
    assert handoff is None
    assert error is not None
    assert "governed JSON handoff" in error


def test_extract_ambiguous_contradictory_candidates_fails() -> None:
    first = dict(_VALID_HANDOFF)
    second = dict(_VALID_HANDOFF)
    second["summary"] = "contradictory summary"
    text = json.dumps(first) + "\n" + json.dumps(second)
    handoff, error = extract_governed_handoff(text)
    assert handoff is None
    assert error is not None
    assert "ambiguous" in error


def test_extract_bounds_summary_and_diagnostic() -> None:
    huge = dict(_VALID_HANDOFF)
    huge["summary"] = "x" * 9000
    handoff, error = extract_governed_handoff(json.dumps(huge))
    assert error is None
    assert handoff is not None
    assert len(handoff["summary"]) == 4000

    _, fail_error = extract_governed_handoff("not json at all " + ("y" * 5000))
    assert fail_error is not None
    assert len(fail_error) <= 2000
