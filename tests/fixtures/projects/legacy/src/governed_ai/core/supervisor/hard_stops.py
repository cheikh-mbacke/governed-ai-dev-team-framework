"""Hard-stop vocabulary shared by recovery and the supervisor daemon."""

from __future__ import annotations

HARD_STOPS = frozenset(
    {
        "budget_exhausted",
        "preflight_failed",
        "kill_switch",
        "authorization_violation",
        "forbidden_secret_access",
        "protected_environment_target",
        "state_corruption",
        "worker_isolation_unguaranteed",
    }
)

RECOVERABLE_STOPS = frozenset(
    {
        "orchestrator_process_failure",
        "stalled_no_progress",
        "out_of_workspace_write",
        "repeated_systemic_failure",
    }
)
