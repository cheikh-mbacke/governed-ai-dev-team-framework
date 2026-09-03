"""Command handler registry."""

from __future__ import annotations

from governed_ai.core.commands.handlers.acquire_worker_lease import handle_acquire_worker_lease
from governed_ai.core.commands.handlers.close_run import handle_close_run
from governed_ai.core.commands.handlers.create_decision_request import handle_create_decision_request
from governed_ai.core.commands.handlers.create_work_unit import handle_create_work_unit
from governed_ai.core.commands.handlers.escalate_work_unit_risk import handle_escalate_work_unit_risk
from governed_ai.core.commands.handlers.export_feedback import handle_export_feedback
from governed_ai.core.commands.handlers.generate_retrospective import handle_generate_retrospective
from governed_ai.core.commands.handlers.submit_feedback import handle_submit_feedback
from governed_ai.core.commands.handlers.issue_run_authorization_grant import (
    handle_issue_run_authorization_grant,
)
from governed_ai.core.commands.handlers.open_run import handle_open_run
from governed_ai.core.commands.handlers.record_acceptance import handle_record_acceptance
from governed_ai.core.commands.handlers.record_execution_attempt import handle_record_execution_attempt
from governed_ai.core.commands.handlers.record_gate_decision import handle_record_gate_decision
from governed_ai.core.commands.handlers.record_integration_merge import (
    handle_record_integration_merge,
)
from governed_ai.core.commands.handlers.record_mission_artifact_challenge import (
    handle_record_mission_artifact_challenge,
)
from governed_ai.core.commands.handlers.record_observation import handle_record_observation
from governed_ai.core.commands.handlers.record_worker_heartbeat import (
    handle_record_worker_heartbeat,
)
from governed_ai.core.commands.handlers.release_worker_lease import handle_release_worker_lease
from governed_ai.core.commands.handlers.register_evidence import handle_register_evidence
from governed_ai.core.commands.handlers.register_finding import handle_register_finding
from governed_ai.core.commands.handlers.register_mission_artifact import (
    handle_register_mission_artifact,
)
from governed_ai.core.commands.handlers.register_release_candidate import handle_register_release_candidate
from governed_ai.core.commands.handlers.resolve_decision_request import handle_resolve_decision_request
from governed_ai.core.commands.handlers.resolve_run_decision import handle_resolve_run_decision
from governed_ai.core.commands.handlers.revoke_run_authorization_grant import (
    handle_revoke_run_authorization_grant,
)
from governed_ai.core.commands.handlers.tighten_execution_ceiling import (
    handle_tighten_execution_ceiling,
)
from governed_ai.core.commands.handlers.transition_work_unit import handle_transition_work_unit
from governed_ai.core.commands.handlers.write_checkpoint import handle_write_checkpoint

HANDLERS = {
    "CreateWorkUnit": handle_create_work_unit,
    "EscalateWorkUnitRisk": handle_escalate_work_unit_risk,
    "TransitionWorkUnit": handle_transition_work_unit,
    "CreateDecisionRequest": handle_create_decision_request,
    "ResolveDecisionRequest": handle_resolve_decision_request,
    "RecordGateDecision": handle_record_gate_decision,
    "RecordAcceptance": handle_record_acceptance,
    "RegisterReleaseCandidate": handle_register_release_candidate,
    "GenerateRetrospective": handle_generate_retrospective,
    "ExportFeedback": handle_export_feedback,
    "SubmitFeedback": handle_submit_feedback,
    "RegisterFinding": handle_register_finding,
    "RecordObservation": handle_record_observation,
    "RegisterEvidence": handle_register_evidence,
    "OpenRun": handle_open_run,
    "AcquireWorkerLease": handle_acquire_worker_lease,
    "RecordExecutionAttempt": handle_record_execution_attempt,
    "WriteCheckpoint": handle_write_checkpoint,
    "CloseRun": handle_close_run,
    "IssueRunAuthorizationGrant": handle_issue_run_authorization_grant,
    "RevokeRunAuthorizationGrant": handle_revoke_run_authorization_grant,
    "ResolveRunDecision": handle_resolve_run_decision,
    "TightenExecutionCeiling": handle_tighten_execution_ceiling,
    "RecordIntegrationMerge": handle_record_integration_merge,
    "RecordWorkerHeartbeat": handle_record_worker_heartbeat,
    "ReleaseWorkerLease": handle_release_worker_lease,
    "RegisterMissionArtifact": handle_register_mission_artifact,
    "RecordMissionArtifactChallenge": handle_record_mission_artifact_challenge,
}
