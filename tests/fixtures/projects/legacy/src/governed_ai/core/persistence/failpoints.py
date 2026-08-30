"""Deterministic transaction failpoints for TX-001..TX-009 tests."""

from __future__ import annotations

from enum import Enum


class TransactionFailpointError(RuntimeError):
    """Simulated process crash at a named transaction step."""


class Failpoint(str, Enum):
    BEFORE_JOURNAL = "before_journal"
    AFTER_JOURNAL = "after_journal"
    AFTER_STAGING = "after_staging"
    AFTER_REPLACE = "after_replace"
    BEFORE_DOMAIN_EVENTS = "before_domain_events"
    AFTER_DOMAIN_EVENTS = "after_domain_events"


_active: Failpoint | None = None
_active_index: int | None = None


def activate_failpoint(name: Failpoint, *, index: int | None = None) -> None:
    global _active, _active_index
    _active = name
    _active_index = index


def clear_failpoints() -> None:
    global _active, _active_index
    _active = None
    _active_index = None


def check_failpoint(name: Failpoint, *, index: int = 0) -> None:
    if _active != name:
        return
    if _active_index is not None and _active_index != index:
        return
    raise TransactionFailpointError(name.value)
