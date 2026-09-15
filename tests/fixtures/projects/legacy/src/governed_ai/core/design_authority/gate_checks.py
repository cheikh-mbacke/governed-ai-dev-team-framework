"""Design Authority gate checks for G1 / G4 / Done."""

from __future__ import annotations

from typing import Any

from governed_ai.core.design_authority.contract import load_design_contract, unwrap
from governed_ai.core.design_authority.divergences import report_blocks_progress
from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.paths import design_root
from governed_ai.core.persistence.io import load_yaml
from governed_ai.core.workspace import Workspace


def _latest_vcr_for_work_unit(
    workspace: Workspace, work_unit_id: str
) -> dict[str, Any] | None:
    conf_dir = design_root(workspace) / "conformance"
    if not conf_dir.is_dir():
        return None
    candidates: list[dict[str, Any]] = []
    for path in conf_dir.glob("*.yaml"):
        report = load_yaml(path)
        if not isinstance(report, dict):
            continue
        if str(report.get("work_unit_id") or "") != work_unit_id:
            continue
        if str(report.get("status") or "") == "obsolete":
            continue
        candidates.append(report)
    if not candidates:
        return None
    candidates.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return candidates[0]


def _coverage_failures(contract: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    """When contract/binding requires multi-state/viewport coverage, verify captures."""
    failures: list[dict[str, Any]] = []
    mode = str(contract.get("design_mode") or "")
    if mode not in {"conform", "adapt"}:
        return failures

    required_states = [str(s) for s in (unwrap(contract.get("states")) or [])]
    required_viewports = unwrap(contract.get("viewports")) or []
    viewport_names = [
        str(v.get("name") if isinstance(v, dict) else v) for v in required_viewports
    ]
    routes = [str(r) for r in (unwrap(contract.get("routes")) or [])]
    # Empty axes collapse to a single placeholder so partial contracts still check.
    route_axis = routes or [""]
    state_axis = required_states or [""]
    viewport_axis = viewport_names or [""]

    observed: set[tuple[str, str, str]] = set()
    for capture in report.get("captures") or []:
        if not isinstance(capture, dict):
            continue
        observed.add(
            (
                str(capture.get("route") or ""),
                str(capture.get("state") or ""),
                str(
                    (capture.get("viewport") or {}).get("name")
                    if isinstance(capture.get("viewport"), dict)
                    else capture.get("viewport")
                    or ""
                ),
            )
        )

    for route in route_axis:
        for state in state_axis:
            for vname in viewport_axis:
                key = (route, state, vname)
                if key not in observed:
                    failures.append(
                        {
                            "code": "incomplete_visual_coverage",
                            "message": (
                                f"missing capture for route={route!r} "
                                f"state={state!r} viewport={vname!r}"
                            ),
                            "details": {
                                "route": route,
                                "state": state,
                                "viewport": vname,
                            },
                        }
                    )
    return failures


def verify_visual_conformance_for_work_unit(
    workspace: Workspace,
    work_unit: dict[str, Any],
    *,
    expected_commit_sha: str | None = None,
) -> dict[str, Any]:
    """Core-owned verification of the latest Visual Conformance Report for a WU."""
    failures: list[dict[str, Any]] = []
    work_unit_id = str(work_unit.get("id") or "")
    binding = work_unit.get("design_binding") or {}
    mode = str(binding.get("design_mode") or binding.get("mode") or "")

    if mode not in {"conform", "adapt"}:
        return {
            "ok": True,
            "applicable": False,
            "failures": [],
            "work_unit_id": work_unit_id,
        }

    report = _latest_vcr_for_work_unit(workspace, work_unit_id)
    if report is None:
        return {
            "ok": False,
            "applicable": True,
            "failures": [
                {
                    "code": "missing_visual_conformance_report",
                    "message": "no fresh visual conformance report for work unit",
                }
            ],
            "work_unit_id": work_unit_id,
        }

    # Recompute report_hash — do not trust the stored field alone.
    recomputed_hash = sha256_canonical(
        {k: v for k, v in report.items() if k != "report_hash"}
    )
    if recomputed_hash != str(report.get("report_hash") or ""):
        failures.append(
            {
                "code": "report_hash_mismatch",
                "message": "visual conformance report_hash does not match document",
                "expected": recomputed_hash,
                "actual": report.get("report_hash"),
            }
        )

    contract_id = str(
        report.get("design_contract_id") or binding.get("design_contract_id") or ""
    )
    if not contract_id:
        failures.append(
            {
                "code": "missing_design_contract",
                "message": "report/binding missing design_contract_id",
            }
        )
        return {
            "ok": False,
            "applicable": True,
            "failures": failures,
            "work_unit_id": work_unit_id,
            "report_id": report.get("report_id"),
        }

    try:
        contract = load_design_contract(workspace, contract_id)
    except Exception as exc:  # noqa: BLE001
        failures.append(
            {
                "code": "design_contract_unavailable",
                "message": str(exc),
                "design_contract_id": contract_id,
            }
        )
        return {
            "ok": False,
            "applicable": True,
            "failures": failures,
            "work_unit_id": work_unit_id,
            "report_id": report.get("report_id"),
        }

    current_hash = str(contract.get("contract_hash") or "")
    if str(report.get("design_contract_hash") or "") != current_hash:
        failures.append(
            {
                "code": "design_contract_hash_mismatch",
                "message": "report design_contract_hash does not match current contract",
                "expected": current_hash,
                "actual": report.get("design_contract_hash"),
            }
        )

    expected_sha = expected_commit_sha
    if expected_sha is None:
        # work_unit["evidence"] is a list of evidence-ref strings, not a
        # commit_sha source — only outcomes/delivery carry the delivered SHA.
        expected_sha = str(
            (work_unit.get("outcomes") or {}).get("delivered_commit_sha")
            or (work_unit.get("delivery") or {}).get("commit_sha")
            or ""
        ) or None
    if expected_sha and str(report.get("commit_sha") or "") != expected_sha:
        failures.append(
            {
                "code": "commit_sha_mismatch",
                "message": "report commit_sha does not match expected delivered HEAD",
                "expected": expected_sha,
                "actual": report.get("commit_sha"),
            }
        )

    implementer = report.get("implementer_role")
    verifier = report.get("verifier_role")
    if implementer and verifier and str(implementer) == str(verifier):
        failures.append(
            {
                "code": "same_actor_implementation_and_verification",
                "message": "implementer_role must differ from verifier_role",
                "role": verifier,
            }
        )

    divergences = list(report.get("divergences") or [])
    # Never trust stored blocks_progress alone — recompute from divergences.
    blocks = report_blocks_progress(divergences)
    if blocks or str(report.get("status") or "") != "passed":
        failures.append(
            {
                "code": "visual_conformance_not_passed",
                "message": "visual conformance must pass with no blocking divergences",
                "status": report.get("status"),
                "blocks_progress_recomputed": blocks,
                "blocks_progress_claimed": report.get("blocks_progress"),
            }
        )

    reqs = binding.get("conformance_requirements") or {}
    if reqs.get("require_multi_viewport", True) or reqs.get("require_required_states", True):
        failures.extend(_coverage_failures(contract, report))

    ok = not failures
    return {
        "ok": ok,
        "applicable": True,
        "failures": failures,
        "work_unit_id": work_unit_id,
        "report_id": report.get("report_id"),
        "blocks_progress": blocks,
    }
