"""Command handler registry."""

from __future__ import annotations

from governed_ai.core.commands.handlers.create_decision_request import handle_create_decision_request
from governed_ai.core.commands.handlers.create_work_unit import handle_create_work_unit
from governed_ai.core.commands.handlers.export_feedback import handle_export_feedback
from governed_ai.core.commands.handlers.generate_retrospective import handle_generate_retrospective
from governed_ai.core.commands.handlers.record_acceptance import handle_record_acceptance
from governed_ai.core.commands.handlers.record_gate_decision import handle_record_gate_decision
from governed_ai.core.commands.handlers.record_observation import handle_record_observation
from governed_ai.core.commands.handlers.register_evidence import handle_register_evidence
from governed_ai.core.commands.handlers.register_finding import handle_register_finding
from governed_ai.core.commands.handlers.register_release_candidate import handle_register_release_candidate
from governed_ai.core.commands.handlers.resolve_decision_request import handle_resolve_decision_request
from governed_ai.core.commands.handlers.transition_work_unit import handle_transition_work_unit

HANDLERS = {
    "CreateWorkUnit": handle_create_work_unit,
    "TransitionWorkUnit": handle_transition_work_unit,
    "CreateDecisionRequest": handle_create_decision_request,
    "ResolveDecisionRequest": handle_resolve_decision_request,
    "RecordGateDecision": handle_record_gate_decision,
    "RecordAcceptance": handle_record_acceptance,
    "RegisterReleaseCandidate": handle_register_release_candidate,
    "GenerateRetrospective": handle_generate_retrospective,
    "ExportFeedback": handle_export_feedback,
    "RegisterFinding": handle_register_finding,
    "RecordObservation": handle_record_observation,
    "RegisterEvidence": handle_register_evidence,
}
