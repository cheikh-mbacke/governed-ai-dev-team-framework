"""Global stop conditions vocabulary (Document 6 §9.5, §11).

A Run stops entirely — never just the affected Work Unit — only on one of
these fixed, Core-recognized conditions. An agent can observe and report a
symptom; it can never invent a new justification to stop a Run. Each of
these triggers an immediate alert, distinct from the grouped morning report.
"""

from __future__ import annotations

GLOBAL_STOP_CONDITIONS = frozenset(
    {
        "budget_exhausted",
        "preflight_failed",
        "kill_switch",
        "authorization_violation",
        "state_corruption",
        "fencing_conflict",
        "forbidden_secret_access",
        "out_of_workspace_write",
        "protected_environment_target",
        "repeated_systemic_failure",
        "worker_isolation_unguaranteed",
    }
)
