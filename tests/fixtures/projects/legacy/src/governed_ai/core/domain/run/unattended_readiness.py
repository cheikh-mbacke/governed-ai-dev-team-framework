"""Definition of Unattended-Ready — the hardened G1 dashboard for night-mode
sessions (Document 6 §6.3).

`build_unattended_readiness_report` is read-only and side-effect-free; it can
be called before a Run/grant even exist (e.g. via the Gateway
``unattended-readiness`` query). OpenRun additionally refuses to start an
unattended Run while any gap remains — the dashboard is both human-facing
preparation evidence and a mechanical gate at session open
(``.ai-team/constitution/definition-of-unattended-ready.yaml``).
"""

from __future__ import annotations

from typing import Any

from governed_ai.core.domain.run.mission_artifact import is_approved

UNATTENDED_PRESETS = (
    "unattended_conservative",
    "unattended_extended",
    "unattended_maximal",
    "custom",
)

# Document 6 §6.1/§6.3 — which mission artifact kinds must back each preset.
# This is this implementation's own reading of §6.1's per-kind "obligatoire
# à partir de <preset>" thresholds, kept in one place so it is easy to revise
# without hunting through handler code.
REQUIRED_ARTIFACT_KINDS_BY_PRESET: dict[str, frozenset[str]] = {
    "unattended_conservative": frozenset(
        {"mission_contract", "execution_envelope", "delivery_contract"}
    ),
    "unattended_extended": frozenset(
        {
            "mission_contract",
            "acceptance_oracle",
            "decision_menu",
            "execution_envelope",
            "delivery_contract",
        }
    ),
    "unattended_maximal": frozenset(
        {
            "mission_contract",
            "acceptance_oracle",
            "decision_menu",
            "tradeoff_policy",
            "execution_envelope",
            "delivery_contract",
        }
    ),
    "custom": frozenset(
        {
            "mission_contract",
            "acceptance_oracle",
            "decision_menu",
            "tradeoff_policy",
            "execution_envelope",
            "delivery_contract",
        }
    ),
}


def work_unit_readiness_gaps(
    work_unit_id: str,
    work_unit: dict[str, Any] | None,
    *,
    has_explicit_ceiling: bool,
) -> list[str]:
    if work_unit is None:
        return [f"{work_unit_id}: work unit not found"]
    gaps = []
    if not (work_unit.get("risk") or {}).get("class"):
        gaps.append(f"{work_unit_id}: missing risk.class")
    scope = work_unit.get("scope") or {}
    if not scope.get("include"):
        gaps.append(f"{work_unit_id}: scope.include is empty (scope not closed)")
    if not has_explicit_ceiling:
        gaps.append(f"{work_unit_id}: no explicit execution_ceiling declared for this run")
    return gaps


def mission_artifact_gaps(preset: str, mission_artifacts: list[dict[str, Any]]) -> list[str]:
    required = REQUIRED_ARTIFACT_KINDS_BY_PRESET.get(preset, frozenset())
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for artifact in mission_artifacts:
        by_kind.setdefault(artifact["kind"], []).append(artifact)
    gaps = []
    for kind in sorted(required):
        candidates = by_kind.get(kind, [])
        if not candidates:
            gaps.append(f"missing mission artifact of kind {kind!r}")
        elif (
            preset in {"unattended_extended", "unattended_maximal", "custom"}
            and not any(is_approved(artifact) for artifact in candidates)
        ):
            gaps.append(
                f"mission artifact of kind {kind!r} exists but has not been "
                "approved by an independent challenge"
            )
    return gaps


def budget_gaps(grant: dict[str, Any]) -> list[str]:
    if grant.get("maximum_spend") is None and grant.get("maximum_duration_hours") is None:
        return ["grant has no explicit budget (maximum_spend and maximum_duration_hours both unset)"]
    return []


def decision_menu_gaps(preset: str, mission_artifacts: list[dict[str, Any]]) -> list[str]:
    if preset == "unattended_conservative":
        return []
    menu = next((item for item in mission_artifacts if item.get("kind") == "decision_menu"), None)
    if menu is None:
        return ["decision menu coverage is unavailable"]
    content = menu.get("content") or {}
    anticipated = int(content.get("anticipated_forks") or 0)
    entries = content.get("entries") or []
    coverage = float(content.get("coverage_percent") or 0)
    if anticipated and len(entries) < anticipated:
        return ["decision menu does not cover every anticipated fork"]
    required = 100.0 if preset in {"unattended_maximal", "custom"} else 80.0
    if coverage < required:
        return [f"decision menu coverage {coverage:g}% is below required {required:g}%"]
    return []


def build_unattended_readiness_report(
    *,
    preset: str,
    work_unit_documents: dict[str, dict[str, Any] | None],
    execution_ceilings_by_work_unit: dict[str, Any] | None,
    grant: dict[str, Any],
    mission_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    ceilings = execution_ceilings_by_work_unit or {}
    gaps: list[str] = []
    for work_unit_id, work_unit in work_unit_documents.items():
        gaps.extend(
            work_unit_readiness_gaps(
                work_unit_id, work_unit, has_explicit_ceiling=work_unit_id in ceilings
            )
        )
    gaps.extend(mission_artifact_gaps(preset, mission_artifacts))
    gaps.extend(decision_menu_gaps(preset, mission_artifacts))
    gaps.extend(budget_gaps(grant))
    eligible = sum(
        1
        for work_unit_id, work_unit in work_unit_documents.items()
        if not work_unit_readiness_gaps(
            work_unit_id,
            work_unit,
            has_explicit_ceiling=work_unit_id in ceilings,
        )
    )
    total = len(work_unit_documents)
    decision_artifact = next(
        (item for item in mission_artifacts if item.get("kind") == "decision_menu"), None
    )
    decision_content = (decision_artifact or {}).get("content") or {}
    coverage = float(decision_content.get("coverage_percent") or 0)
    execution_artifact = next(
        (item for item in mission_artifacts if item.get("kind") == "execution_envelope"), None
    )
    execution_content = (execution_artifact or {}).get("content") or {}
    manual_commands = list(execution_content.get("manual_confirmation_commands") or [])
    necessarily_human = [
        "product_decisions",
        "constitution_changes",
        "protected_branch_merge",
        "production_actions",
        "G2",
        "G3",
        "G4",
    ]
    completion_targets = {
        "unattended_conservative": "verified_work_unit_branch",
        "unattended_extended": "verified_integration_branch",
        "unattended_maximal": "verified_release_candidate",
        "custom": "constitution_bounded_custom_target",
    }
    return {
        "preset": preset,
        "ready": not gaps,
        "gaps": gaps,
        "work_unit_ids": sorted(work_unit_documents),
        "eligible_work_units_percent": round((eligible / total * 100) if total else 0.0, 2),
        "anticipated_fork_coverage_percent": coverage,
        "commands_requiring_manual_confirmation": manual_commands,
        "estimated_blocking_probability_percent": max(0.0, min(100.0, 100.0 - coverage)),
        "maximum_realistic_delivery_target": completion_targets.get(preset),
        "decisions_remaining_human": necessarily_human,
    }
