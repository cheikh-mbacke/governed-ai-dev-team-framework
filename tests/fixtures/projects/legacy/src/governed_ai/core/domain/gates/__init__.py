"""Gate domain helpers."""

G4_COMPLETION_STATUSES = frozenset({"approved", "passed", "accepted"})

GATE_STATUS_BY_GATE = {
    "G0": frozenset({"passed", "failed", "rejected", "changes_requested"}),
    "G1": frozenset({"approved", "rejected", "changes_requested"}),
    "G2": frozenset({"approved", "rejected", "changes_requested", "not_required"}),
    "G3": frozenset({"approved", "rejected", "changes_requested", "not_required", "passed", "failed"}),
    "G4": frozenset(
        {
            "approved",
            "rejected",
            "changes_requested",
            "passed",
            "failed",
            "partial",
            "partially_accepted",
            "not_required",
            "accepted",
            "remediation_required",
        }
    ),
}

HUMAN_ACCEPTANCE_BY_GATE_STATUS = {
    "approved": "accepted",
    "passed": "accepted",
    "accepted": "accepted",
    "rejected": "rejected",
    "failed": "rejected",
    "partial": "partially_accepted",
    "partially_accepted": "partially_accepted",
    "changes_requested": "partially_accepted",
    "remediation_required": "remediation_required",
    "not_required": "accepted",
}
