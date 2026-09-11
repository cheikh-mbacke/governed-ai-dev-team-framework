"""Step timeout resolution and policy hash inclusion (Lot 4)."""

from __future__ import annotations

from governed_ai.core.domain.run.autonomy_policy import (
    DEFAULT_TIMEOUTS_SECONDS_BY_STEP,
    effective_policy_hash,
    resolve_effective_policy,
    resolve_step_timeout_seconds,
)


def test_resolve_step_timeout_seconds_sandbox_implementation() -> None:
    policy = resolve_effective_policy("unattended_conservative")
    assert resolve_step_timeout_seconds(policy, "sandbox_implementation") == 5400.0
    assert DEFAULT_TIMEOUTS_SECONDS_BY_STEP["sandbox_implementation"] == 5400


def test_timeouts_are_included_in_policy_hash() -> None:
    base = resolve_effective_policy("unattended_conservative")
    altered = resolve_effective_policy(
        "unattended_conservative",
        overrides={
            "execution": {
                "timeouts_seconds_by_step": {
                    **DEFAULT_TIMEOUTS_SECONDS_BY_STEP,
                    "sandbox_implementation": 1000,
                }
            }
        },
    )
    assert effective_policy_hash(base) != effective_policy_hash(altered)
