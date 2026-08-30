"""Invisible-blocking preflight enforcement (Document 6 §9.6).

A Run's ``preflight`` payload is a heterogeneous, adapter-produced report:
a mapping of check name to either a plain value or a ``{"status", "detail"}``
entry. The Core never inspects *how* an adapter determined a status — it
only enforces, mechanically, that no check is left in a state that could
mask a blocking tool-confirmation prompt during an unattended session.
"""

from __future__ import annotations

from typing import Any

BLOCKING_PREFLIGHT_STATUSES = frozenset({"fail", "blocked", "manual"})


def blocking_preflight_checks(preflight: dict[str, Any]) -> list[str]:
    """Return the names of preflight checks that must block an unattended Run."""
    blocking: list[str] = []
    for name, entry in preflight.items():
        if isinstance(entry, dict) and entry.get("status") in BLOCKING_PREFLIGHT_STATUSES:
            blocking.append(name)
    return sorted(blocking)
