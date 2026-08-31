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
    {"unattended_conservative", "unattended_extended", "unattended_maximal"}
)

_WINDOWS = {
    "unattended_conservative": 8,
    "unattended_extended": 10,
    "unattended_maximal": 12,
}


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
                if preset == "unattended_maximal"
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
                    if preset in {"unattended_extended", "unattended_maximal"}
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
        ],
        "global_stop_behavior": "immediate_alert_plus_stop",
        "completion": {
            "target": (
                "verified_release_candidate"
                if preset == "unattended_maximal"
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


def effective_policy_hash(policy: dict[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(policy)).hexdigest()}"
