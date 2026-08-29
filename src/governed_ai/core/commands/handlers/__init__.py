"""Command handler registry."""

from __future__ import annotations

from governed_ai.core.commands.handlers.transition_work_unit import handle_transition_work_unit

HANDLERS = {
    "TransitionWorkUnit": handle_transition_work_unit,
}
