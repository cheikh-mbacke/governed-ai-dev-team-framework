"""Persistent Supervisor Daemon for unattended Runs.

Operational control plane only. Authoritative mutations still go through
``CommandGateway``. Durable daemon state lives under ``.ai-team/supervisor/``.
"""

from __future__ import annotations

from governed_ai.core.supervisor.daemon import SupervisorDaemon
from governed_ai.core.supervisor.hard_stops import HARD_STOPS, RECOVERABLE_STOPS
from governed_ai.core.supervisor.protocol import WorkerAttemptState

__all__ = [
    "HARD_STOPS",
    "RECOVERABLE_STOPS",
    "SupervisorDaemon",
    "WorkerAttemptState",
]
