"""Read legacy Gate Decision audit records without rewriting them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

GATE_DECISION_REQUIRED = ("id", "gate", "status", "by", "at")
VALID_GATES = frozenset({"G0", "G1", "G2", "G3", "G4"})


def is_gate_decision_document(document: dict[str, Any]) -> bool:
    """Return True when the document is an immutable gate audit record."""
    if not isinstance(document, dict):
        return False
    if document.get("type") == "GATE_DECISION_REQUEST":
        return False
    if not all(field in document for field in GATE_DECISION_REQUIRED):
        return False
    return document.get("gate") in VALID_GATES


def read_gate_decision(path: Path) -> dict[str, Any]:
    """Load a gate decision audit record from disk without mutation."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: gate decision must be a mapping")
    if not is_gate_decision_document(document):
        raise ValueError(f"{path}: not a legacy gate decision audit record")
    return document
