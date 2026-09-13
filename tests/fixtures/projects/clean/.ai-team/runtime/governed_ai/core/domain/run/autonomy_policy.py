"""Deterministic EffectiveAutonomyPolicy resolution for unattended Runs."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from governed_ai.contracts.bundle_hash import canonical_json_bytes
from governed_ai.core.domain.run.execution_ceiling import (
    DEFAULT_EXECUTION_CEILING,
    validate_execution_ceiling,
)

UNATTENDED_PRESETS = frozenset(
    {"unattended_conservative", "unattended_extended", "unattended_maximal", "custom"}
)

NAMED_AUTONOMY_PRESETS = frozenset({"supervised_copilots", *UNATTENDED_PRESETS})
LEGACY_LEVEL_PRESET = {
    1: "supervised_copilots",
    2: "supervised_copilots",
    3: "unattended_conservative",
}

_WINDOWS = {
    "unattended_conservative": 8,
    "unattended_extended": 10,
    "unattended_maximal": 12,
    "custom": 12,
}

DEFAULT_TIMEOUTS_SECONDS_BY_STEP: dict[str, int] = {
    "sandbox_implementation": 5400,
    "remediation": 3600,
    "verification": 1800,
    "review": 1200,
    "security_review": 1200,
    "audit": 1200,
    "integration_review": 1800,
}
DEFAULT_UNKNOWN_STEP_TIMEOUT_SECONDS = 600
HARD_MAX_TIMEOUT_SECONDS = 7200


def is_unattended_preset(value: object) -> bool:
    """Return whether ``value`` selects any governed unattended policy."""
    return str(value or "") in UNATTENDED_PRESETS


def resolve_project_preset(autonomy: dict[str, Any]) -> str:
    """Resolve the named preset once; legacy ``level`` is compatibility input only.

    When both ``preset`` and ``level`` are present they must agree
    (``LEGACY_LEVEL_PRESET[level] == preset``); divergence is refused so a
    named preset cannot silently mask a conflicting legacy level.
    """
    preset = autonomy.get("preset")
    level = autonomy.get("level")
    if preset is not None:
        if preset not in NAMED_AUTONOMY_PRESETS:
            raise ValueError(f"unsupported autonomy preset: {preset}")
        if level is not None:
            if level not in LEGACY_LEVEL_PRESET:
                raise ValueError(
                    f"legacy autonomy.level must be in 1..3 when set with preset, got {level!r}"
                )
            mapped = LEGACY_LEVEL_PRESET[int(level)]
            if mapped != preset:
                raise ValueError(
                    f"autonomy.preset {preset!r} diverges from legacy autonomy.level "
                    f"{level} (maps to {mapped!r}); remove level or align them"
                )
        return str(preset)
    if level not in LEGACY_LEVEL_PRESET:
        raise ValueError("autonomy.preset or a legacy autonomy.level in 1..3 is required")
    return LEGACY_LEVEL_PRESET[int(level)]


def resolve_effective_policy(
    preset: str,
    *,
    maximum_parallel_workers: int = 4,
    maximum_attempts_per_step: int = 3,
    maximum_remediation_cycles: int = 2,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if preset not in UNATTENDED_PRESETS:
        raise ValueError(f"unsupported unattended preset: {preset}")
    if preset == "custom" and not overrides:
        raise ValueError("custom unattended preset requires explicit policy overrides")
    policy: dict[str, Any] = {
        "autonomy": {
            "preset": preset,
            "unattended_window_hours": _WINDOWS[preset],
        },
        "eligibility": {
            "maximum_risk_class": "critical",
            "risk_reclassification": {
                "escalation": "automatic_immediate",
                "de_escalation": "requires_human_validation",
            },
        },
        "decision_menu": {
            "ref": "decision-menu.yaml",
            "coverage_required": (
                "exhaustive_for_anticipated_forks"
                if preset in {"unattended_maximal", "custom"}
                else "substantial_for_anticipated_forks"
                if preset == "unattended_extended"
                else "bounded_for_anticipated_forks"
            ),
            "unmatched_or_unvalidated_fork_behavior": "block_dependent_subgraph",
            "resolution_mode": "agent_proposes_core_validates",
        },
        "execution_ceiling_default": deepcopy(DEFAULT_EXECUTION_CEILING),
        "decisions": {
            "reversible_technical_choices": "delegated",
            "shared_contract_changes": "bounded",
            "product_decisions": "human_only",
            "constitution_changes": "human_only",
            "production_actions": "human_only",
            "ambiguity": "block_dependent_subgraph",
        },
        "roles": {
            "agents": {
                "force": [
                    "security-reviewer",
                    "auditor",
                    "mandate-matcher",
                    "integration-steward",
                ],
                "force_pre_g1": (
                    ["requirements-challenger"]
                    if preset in {"unattended_extended", "unattended_maximal", "custom"}
                    else []
                ),
            },
            "core_components": {"force": ["run-reliability-controller"]},
        },
        "execution": {
            "maximum_parallel_workers": maximum_parallel_workers,
            "maximum_parallel_critical_wu": 1,
            "heartbeat_seconds": 60,
            "stalled_after_minutes": 15,
            "maximum_attempts_per_step": maximum_attempts_per_step,
            "maximum_remediation_cycles": maximum_remediation_cycles,
            "worker_lease_fencing": "required",
            "timeouts_seconds_by_step": dict(DEFAULT_TIMEOUTS_SECONDS_BY_STEP),
            "default_timeout_seconds": DEFAULT_UNKNOWN_STEP_TIMEOUT_SECONDS,
        },
        "preflight": {"forbid_manual_confirmation_states": True},
        "budgets": {
            "maximum_wall_time_hours": _WINDOWS[preset],
            "maximum_changed_files_per_work_unit": 30,
            "maximum_changed_files_per_critical_work_unit": 10,
            "maximum_new_dependencies": 0,
        },
        "environments": {
            "allowed": ["development", "test"],
            "forbidden": ["staging", "production"],
        },
        "global_stop_conditions": [
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
            "no_dispatchable_work",
            "orchestrator_process_failure",
            "stalled_no_progress",
        ],
        "global_stop_behavior": "immediate_alert_plus_stop",
        "human_feedback": {
            "visual_checkpoints": "non_blocking",
            "pending_feedback_behavior": "reconcile_before_next_affected_dispatch",
            "continue_unaffected_work": True,
            "may_reduce_execution_ceiling": False,
        },
        "completion": {
            "target": (
                "verified_release_candidate"
                if preset in {"unattended_maximal", "custom"}
                else "verified_integration_branch"
                if preset == "unattended_extended"
                else "verified_work_unit_branch"
            ),
            "morning_report": True,
        },
    }
    if overrides:
        policy = _merge(policy, overrides)
    _validate_invariants(policy)
    return policy


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _validate_invariants(policy: dict[str, Any]) -> None:
    environments = policy.get("environments") or {}
    if set(environments.get("allowed") or []) & {"staging", "production"}:
        raise ValueError("staging and production can never be allowed unattended")
    if not {"staging", "production"}.issubset(set(environments.get("forbidden") or [])):
        raise ValueError("staging and production must be explicitly forbidden")
    decision_menu = policy.get("decision_menu") or {}
    if decision_menu.get("resolution_mode") != "agent_proposes_core_validates":
        raise ValueError("decision resolution must remain agent_proposes_core_validates")
    if decision_menu.get("unmatched_or_unvalidated_fork_behavior") != "block_dependent_subgraph":
        raise ValueError("unmatched decisions must block their dependent subgraph")
    execution = policy.get("execution") or {}
    if execution.get("worker_lease_fencing") != "required":
        raise ValueError("worker lease fencing is required")
    if execution.get("maximum_parallel_critical_wu") != 1:
        raise ValueError("critical Work Unit parallelism must remain one")
    timeouts = execution.get("timeouts_seconds_by_step") or {}
    if not isinstance(timeouts, dict):
        raise ValueError("execution.timeouts_seconds_by_step must be an object")
    for step_name, seconds in timeouts.items():
        if not isinstance(step_name, str) or not step_name:
            raise ValueError("timeout step names must be non-empty strings")
        if not isinstance(seconds, (int, float)) or float(seconds) <= 0:
            raise ValueError(f"timeout for {step_name!r} must be a positive number")
        if float(seconds) > HARD_MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout for {step_name!r} exceeds hard max {HARD_MAX_TIMEOUT_SECONDS}s"
            )
    default_timeout = execution.get("default_timeout_seconds")
    if default_timeout is not None and (
        not isinstance(default_timeout, (int, float)) or float(default_timeout) <= 0
    ):
        raise ValueError("execution.default_timeout_seconds must be a positive number")
    ceiling_violation = validate_execution_ceiling(
        policy.get("execution_ceiling_default") or {}
    )
    if ceiling_violation is not None:
        raise ValueError(ceiling_violation)
    decisions = policy.get("decisions") or {}
    for field in ("product_decisions", "constitution_changes", "production_actions"):
        if decisions.get(field) != "human_only":
            raise ValueError(f"decisions.{field} must remain human_only")
    if policy.get("global_stop_behavior") != "immediate_alert_plus_stop":
        raise ValueError("global stop behavior must remain immediate_alert_plus_stop")
    human_feedback = policy.get("human_feedback") or {}
    if human_feedback.get("visual_checkpoints") != "non_blocking":
        raise ValueError("formative visual checkpoints must remain non-blocking unattended")
    if human_feedback.get("pending_feedback_behavior") != (
        "reconcile_before_next_affected_dispatch"
    ):
        raise ValueError("received human feedback must be reconciled before affected dispatch")
    if human_feedback.get("continue_unaffected_work") is not True:
        raise ValueError("unaffected work must continue during human feedback reconciliation")
    if human_feedback.get("may_reduce_execution_ceiling") is not False:
        raise ValueError("formative human feedback cannot implicitly reduce execution ceiling")


def effective_policy_hash(policy: dict[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(policy)).hexdigest()}"


def resolve_step_timeout_seconds(
    policy: dict[str, Any] | None,
    step: str,
    *,
    grant_remaining_seconds: float | None = None,
) -> float:
    """Resolve the effective adapter timeout for one dispatch step."""
    execution = (policy or {}).get("execution") or {}
    by_step = execution.get("timeouts_seconds_by_step") or {}
    raw = by_step.get(
        step, execution.get("default_timeout_seconds", DEFAULT_UNKNOWN_STEP_TIMEOUT_SECONDS)
    )
    timeout = float(raw)
    timeout = max(1.0, min(timeout, float(HARD_MAX_TIMEOUT_SECONDS)))
    if grant_remaining_seconds is not None:
        timeout = max(1.0, min(timeout, float(grant_remaining_seconds)))
    return timeout
