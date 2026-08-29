"""Command handler registry."""

from __future__ import annotations

from governed_ai.core.commands.handlers.record_observation import handle_record_observation
from governed_ai.core.commands.handlers.register_evidence import handle_register_evidence
from governed_ai.core.commands.handlers.transition_work_unit import handle_transition_work_unit

HANDLERS = {
    "TransitionWorkUnit": handle_transition_work_unit,
    "RecordObservation": handle_record_observation,
    "RegisterEvidence": handle_register_evidence,
}
