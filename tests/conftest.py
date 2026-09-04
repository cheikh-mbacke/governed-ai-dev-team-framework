"""Test harness path setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from distribution.installer.assessment import ASSESSMENT_SKIP_ENV

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_AI_TEAM = ROOT / "distribution" / "payload" / ".ai-team"
FABRIC_ROOT = ROOT / ".fabric"
for entry in (ROOT, ROOT / "src"):
    text = str(entry)
    if text not in sys.path:
        sys.path.insert(0, text)


@pytest.fixture(autouse=True)
def _skip_assessment_gate_for_install_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh-install CLI requires an assessment report; tests opt out via env.

    Individual tests that assert the gate must clear this variable.
    """
    monkeypatch.setenv(ASSESSMENT_SKIP_ENV, "1")
