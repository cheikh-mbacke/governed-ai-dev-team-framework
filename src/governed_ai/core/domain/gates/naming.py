"""Gate decision naming (Document 13 §6)."""

from __future__ import annotations

import uuid
from governed_ai.compat.datetime import UTC, datetime


def generate_gate_decision_id(gate: str) -> str:
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}"
    suffix = uuid.uuid4().hex[:8]
    return f"gate-{gate.lower()}-{stamp}-{suffix}"
