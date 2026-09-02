"""Datetime helpers compatible with Python 3.10+."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc

__all__ = ["UTC", "datetime", "timedelta", "timezone"]
