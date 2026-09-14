"""Visual Conformance Runner — independent verification against Design Contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from governed_ai.core.design_authority.contract import load_design_contract, unwrap
from governed_ai.core.design_authority.divergences import (
    classify_divergence,
    report_blocks_progress,
)
from governed_ai.core.design_authority.hashing import sha256_bytes, sha256_canonical, sha256_file
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.paths import (
    conformance_path,
    ensure_design_layout,
    evidence_dir,
)
from governed_ai.core.persistence.io import dump_yaml
from governed_ai.core.workspace import Workspace

CaptureFn = Callable[[dict[str, Any]], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConformanceError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _default_capture(spec: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stub capture used when no browser automation is available."""
    payload = {
        "route": spec.get("route"),
        "state": spec.get("state"),
        "viewport": spec.get("viewport"),
        "dom": spec.get("observed_dom") or {},
        "styles": spec.get("observed_styles") or {},
        "text": spec.get("observed_text") or [],
        "components": spec.get("observed_components") or [],
        "screenshot_bytes": spec.get("screenshot_bytes"),
    }
    return payload


def _write_capture_evidence(
    directory: Path,
    *,
    label: str,
    capture: dict[str, Any],
    commit_sha: str,
    reference_id: str | None,
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    meta = {
        "label": label,
        "route": capture.get("route"),
        "state": capture.get("state"),
        "viewport": capture.get("viewport"),
        "commit_sha": commit_sha,
        "reference_id": reference_id,
        "captured_at": _now_iso(),
    }
    screenshot = capture.get("screenshot_bytes")
    screenshot_hash = None
    screenshot_path = None
    if isinstance(screenshot, (bytes, bytearray)):
        screenshot_path = directory / f"{label}.png"
        screenshot_path.write_bytes(bytes(screenshot))
        screenshot_hash = sha256_file(screenshot_path)
    dom_path = directory / f"{label}.dom.json"
    dom_path.write_text(
        json.dumps(
            {
                "dom": capture.get("dom") or {},
                "styles": capture.get("styles") or {},
                "text": capture.get("text") or [],
                "components": capture.get("components") or [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    meta_path = directory / f"{label}.meta.yaml"
    dump_yaml(meta_path, meta)
    return {
        "label": label,
        "route": capture.get("route"),
        "state": capture.get("state"),
        "viewport": capture.get("viewport"),
        "commit_sha": commit_sha,
        "reference_id": reference_id,
        "screenshot_path": str(screenshot_path.as_posix()) if screenshot_path else None,
        "screenshot_hash": screenshot_hash,
        "dom_snapshot_path": dom_path.as_posix(),
        "dom_snapshot_hash": sha256_file(dom_path),
        "meta_path": meta_path.as_posix(),
        "environment": capture.get("environment") or {},
    }


def run_visual_conformance(
    workspace: Workspace,
    *,
    report_id: str,
    design_contract_id: str,
    work_unit_id: str,
    commit_sha: str,
    verifier_role: str,
    implementer_role: str | None = None,
    lease_id: str | None = None,
    epoch: int | None = None,
    expected_lease_id: str | None = None,
    expected_epoch: int | None = None,
    observations: list[dict[str, Any]] | None = None,
    capture_fn: CaptureFn | None = None,
    agent_claimed_passed: bool | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run conformance checks and produce a Core-owned report.

    ``observations`` supplies per viewport/state observed facts (for tests and
    adapters). When omitted, the runner still emits a structural plan and fails
    if required screens/states/viewports lack observations.
    """
    if implementer_role and verifier_role == implementer_role:
        raise ConformanceError(
            "same_actor_implementation_and_verification",
            "frontend-developer cannot be the sole visual verifier of their own work",
            details={"role": verifier_role},
        )
    if expected_lease_id is not None and lease_id != expected_lease_id:
        raise ConformanceError(
            "stale_lease",
            "visual result lease_id does not match current lease",
            details={"expected": expected_lease_id, "actual": lease_id},
        )
    if expected_epoch is not None and epoch != expected_epoch:
        raise ConformanceError(
            "stale_epoch",
            "visual result epoch does not match current epoch",
            details={"expected": expected_epoch, "actual": epoch},
        )

    contract = load_design_contract(workspace, design_contract_id)
    tolerances = unwrap(contract.get("tolerances")) or {}
    level = str(contract.get("conformance_level") or tolerances.get("level") or "tolerant_visual")
    mandatory_text = list(unwrap(contract.get("mandatory_text")) or [])
    mandatory_elements = list(unwrap(contract.get("mandatory_elements")) or [])
    forbidden_elements = list(unwrap(contract.get("forbidden_elements")) or [])
    required_states = list(unwrap(contract.get("states")) or [])
    required_viewports = list(unwrap(contract.get("viewports")) or [])
    routes = list(unwrap(contract.get("routes")) or [])
    auth_refs = [
        r for r in (contract.get("references") or []) if r.get("authority_level") == "authoritative"
    ]
    advisory_refs = [
        r for r in (contract.get("references") or []) if r.get("authority_level") == "advisory"
    ]

    ensure_design_layout(workspace)
    evidence_root = evidence_dir(workspace, report_id)
    capture = capture_fn or _default_capture
    observations = list(observations or [])
    divergences: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    # Multi-viewport / multi-state coverage.
    observed_keys = {
        (
            str(o.get("route") or ""),
            str(o.get("state") or ""),
            str((o.get("viewport") or {}).get("name") or o.get("viewport") or ""),
        )
        for o in observations
    }
    default_route = routes[0] if routes else ""
    for viewport in required_viewports:
        vname = str(viewport.get("name") if isinstance(viewport, dict) else viewport)
        for state in required_states:
            key = (default_route, str(state), vname)
            if key not in observed_keys and contract.get("design_mode") in {"conform", "adapt"}:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level="authoritative" if auth_refs else "advisory",
                        explanation=f"missing verification for state={state!r} viewport={vname!r}",
                        details={"route": default_route, "state": state, "viewport": vname},
                    )
                )

    for index, obs in enumerate(observations):
        captured = capture(obs)
        ref_id = None
        if auth_refs:
            ref_id = str(auth_refs[0].get("design_artifact_id"))
        elif advisory_refs:
            ref_id = str(advisory_refs[0].get("design_artifact_id"))
        evidence = _write_capture_evidence(
            evidence_root / f"capture-{index:02d}",
            label=f"capture-{index:02d}",
            capture={**obs, **captured},
            commit_sha=commit_sha,
            reference_id=ref_id,
        )
        captures.append(evidence)

        authority = "authoritative" if auth_refs else "advisory"
        observed_text = [str(t) for t in (captured.get("text") or obs.get("observed_text") or [])]
        observed_components = [
            str(c) for c in (captured.get("components") or obs.get("observed_components") or [])
        ]

        for text in mandatory_text:
            if text not in observed_text:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level=authority,
                        explanation=f"mandatory text missing: {text!r}",
                        details={"capture": evidence["label"]},
                    )
                )
            else:
                checks.append({"type": "textual", "status": "passed", "text": text})

        for element in mandatory_elements:
            if element not in observed_components:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level=authority,
                        explanation=f"mandatory element missing: {element!r}",
                        details={"capture": evidence["label"]},
                    )
                )
            else:
                checks.append({"type": "component_presence", "status": "passed", "element": element})

        for element in forbidden_elements:
            if element in observed_components:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level=authority,
                        explanation=f"forbidden element present: {element!r}",
                        details={"capture": evidence["label"]},
                    )
                )

        # Image diff only when both reference and observed screenshots exist.
        ref_bytes = obs.get("reference_screenshot_bytes")
        got_bytes = captured.get("screenshot_bytes") or obs.get("screenshot_bytes")
        if isinstance(ref_bytes, (bytes, bytearray)) and isinstance(got_bytes, (bytes, bytearray)):
            if bytes(ref_bytes) == bytes(got_bytes):
                checks.append({"type": "image_comparison", "status": "passed", "diff_ratio": 0.0})
            else:
                threshold = float(tolerances.get("difference_threshold") or 0.02)
                # Byte inequality without a pixel library → treat as full diff unless
                # a precomputed diff_ratio is supplied.
                diff_ratio = float(obs.get("diff_ratio") or 1.0)
                masked = list(tolerances.get("masked_regions") or [])
                dynamic = list(tolerances.get("dynamic_content_selectors") or [])
                if diff_ratio <= threshold:
                    checks.append(
                        {
                            "type": "image_comparison",
                            "status": "passed",
                            "diff_ratio": diff_ratio,
                            "threshold": threshold,
                            "masked_regions": masked,
                        }
                    )
                elif obs.get("allowed_by_tolerance_rule"):
                    divergences.append(
                        classify_divergence(
                            kind="allowed_adaptation",
                            severity="advisory",
                            authority_level=authority,
                            explanation="difference covered by Design Contract tolerance",
                            contract_tolerance_rule=str(obs.get("allowed_by_tolerance_rule")),
                            details={"diff_ratio": diff_ratio, "threshold": threshold},
                        )
                    )
                else:
                    kind = "environment_variance" if obs.get("environment_variance") else "defect"
                    severity = "advisory" if kind == "environment_variance" else "blocking"
                    divergences.append(
                        classify_divergence(
                            kind=kind,
                            severity=severity,
                            authority_level=authority,
                            explanation="visual difference exceeds contract tolerance",
                            details={
                                "diff_ratio": diff_ratio,
                                "threshold": threshold,
                                "masked_regions": masked,
                                "dynamic_content_selectors": dynamic,
                                "reference_hash": sha256_bytes(bytes(ref_bytes)),
                                "observed_hash": sha256_bytes(bytes(got_bytes)),
                            },
                        )
                    )

    # Hostile agent claim: Core recomputes and refuses.
    blocks = report_blocks_progress(divergences)
    if agent_claimed_passed and blocks:
        divergences.append(
            classify_divergence(
                kind="defect",
                severity="blocking",
                authority_level="authoritative" if auth_refs else "advisory",
                explanation="agent claimed passed but Core recomputed blocking divergences",
                details={"agent_claimed_passed": True},
            )
        )
        blocks = True

    # Advisory-only references: never auto-block solely from advisory authority.
    if not auth_refs and advisory_refs:
        for item in divergences:
            if item.get("authority_level") == "advisory":
                item["blocks_progress"] = False
        blocks = report_blocks_progress(divergences)

    status = "failed" if blocks else "passed"
    if not observations and contract.get("design_mode") in {"conform", "adapt"}:
        status = "failed"
        blocks = True

    report = {
        "report_id": report_id,
        "schema_version": SCHEMA_VERSION,
        "design_contract_id": design_contract_id,
        "design_contract_hash": contract.get("contract_hash"),
        "work_unit_id": work_unit_id,
        "commit_sha": commit_sha,
        "verifier_role": verifier_role,
        "implementer_role": implementer_role,
        "lease_id": lease_id,
        "epoch": epoch,
        "conformance_level": level,
        "tolerances": tolerances,
        "checks": checks,
        "captures": captures,
        "divergences": divergences,
        "blocks_progress": blocks,
        "status": status,
        "created_at": _now_iso(),
    }
    report["report_hash"] = sha256_canonical(
        {k: v for k, v in report.items() if k != "report_hash"}
    )
    if persist:
        dump_yaml(conformance_path(workspace, report_id), report)
    return report
