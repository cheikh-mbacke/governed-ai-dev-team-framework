"""Design Contract compiler — versioned, provenance-aware visual obligations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import (
    DESIGN_MODES,
    SCHEMA_VERSION,
)
from governed_ai.core.design_authority.paths import contract_path, ensure_design_layout
from governed_ai.core.design_authority.reference_set import (
    ReferenceSetError,
    load_reference_set,
    validate_reference_members,
)
from governed_ai.core.design_authority.registry import load_artifact
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DesignContractError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _origin_bucket(
    value: Any,
    *,
    origin: str,
    validated_by_human: bool = False,
) -> dict[str, Any]:
    return {
        "value": value,
        "origin": origin,
        "validated_by_human": validated_by_human,
        "authoritative": origin in {"explicitly_provided", "human_decision"}
        and (origin != "proposed_inference"),
    }


def compile_design_contract(
    workspace: Workspace,
    *,
    design_contract_id: str,
    design_mode: str,
    design_reference_set_id: str | None = None,
    authoritative_artifact_ids: list[str] | None = None,
    compiled_by: str,
    screens: list[str] | None = None,
    routes: list[str] | None = None,
    components: list[str] | None = None,
    structure: dict[str, Any] | None = None,
    mandatory_text: list[str] | None = None,
    mandatory_elements: list[str] | None = None,
    forbidden_elements: list[str] | None = None,
    navigation: dict[str, Any] | None = None,
    behaviors: list[str] | None = None,
    states: list[str] | None = None,
    viewports: list[dict[str, Any]] | None = None,
    breakpoints: list[dict[str, Any]] | None = None,
    tokens: dict[str, Any] | None = None,
    typography: dict[str, Any] | None = None,
    colors: dict[str, Any] | None = None,
    spacing: dict[str, Any] | None = None,
    radii: dict[str, Any] | None = None,
    shadows: dict[str, Any] | None = None,
    icons: list[str] | None = None,
    assets: list[str] | None = None,
    responsive_rules: list[str] | None = None,
    accessibility: dict[str, Any] | None = None,
    motion: dict[str, Any] | None = None,
    conformance_level: str = "tolerant_visual",
    tolerances: dict[str, Any] | None = None,
    free_zones: list[dict[str, Any]] | None = None,
    human_decisions_required: list[str] | None = None,
    inferences: list[dict[str, Any]] | None = None,
    design_system_precedence: str = "escalate_on_conflict",
    persist: bool = True,
) -> dict[str, Any]:
    if design_mode not in DESIGN_MODES:
        raise DesignContractError(
            "invalid_design_mode", f"unknown design_mode {design_mode!r}"
        )
    ensure_design_layout(workspace)
    path = contract_path(workspace, design_contract_id)
    if path.is_file():
        raise DesignContractError(
            "already_exists",
            f"design contract {design_contract_id!r} already exists",
        )

    refs: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if design_reference_set_id:
        try:
            ref_set = load_reference_set(workspace, design_reference_set_id)
        except ReferenceSetError as exc:
            raise DesignContractError(exc.code, exc.message, details=exc.details) from exc
        members = list(ref_set.get("members") or [])
        issues.extend(validate_reference_members(workspace, members))
        for member in members:
            aid = str(member.get("design_artifact_id") or "")
            if not aid:
                continue
            artifact = load_artifact(workspace, aid)
            refs.append(
                {
                    "design_artifact_id": aid,
                    "authority_level": artifact.get("authority_level"),
                    "content_hash": artifact.get("content_hash"),
                    "source_path": artifact.get("source_path"),
                    "source_uri": artifact.get("source_uri"),
                    "target": member.get("target") or {},
                }
            )

    for aid in authoritative_artifact_ids or []:
        artifact = load_artifact(workspace, aid)
        refs.append(
            {
                "design_artifact_id": aid,
                "authority_level": artifact.get("authority_level"),
                "content_hash": artifact.get("content_hash"),
                "source_path": artifact.get("source_path"),
                "source_uri": artifact.get("source_uri"),
                "target": {},
            }
        )

    blocking = [i for i in issues if i.get("severity") == "blocking"]
    if design_mode in {"conform", "adapt"} and blocking:
        raise DesignContractError(
            "blocking_reference_issues",
            "cannot compile conform/adapt contract with blocking reference issues",
            details={"issues": blocking},
        )

    auth_refs = [r for r in refs if r.get("authority_level") == "authoritative"]
    if design_mode == "conform" and not auth_refs:
        raise DesignContractError(
            "missing_authoritative_reference",
            "design_mode=conform requires at least one authoritative reference",
        )
    if design_mode == "create" and auth_refs:
        raise DesignContractError(
            "create_blocked_by_authoritative_design",
            "design_mode=create requested while authoritative design references exist; "
            "human decision required",
            details={"authoritative_artifact_ids": [r["design_artifact_id"] for r in auth_refs]},
        )

    # Provenance-tagged fields: caller-supplied content is explicitly provided;
    # inferences stay non-authoritative until human validation.
    tagged_inferences = []
    for item in inferences or []:
        tagged_inferences.append(
            {
                **item,
                "origin": "proposed_inference",
                "authoritative": bool(item.get("validated_by_human")),
            }
        )

    default_tolerances = {
        "level": conformance_level,
        "difference_threshold": 0.02,
        "masked_regions": [],
        "dynamic_content_selectors": [],
        "ignore_antialiasing": True,
        "ignore_platform_font_raster": True,
        "ignore_animation_frames": True,
    }
    if tolerances:
        default_tolerances.update(tolerances)

    default_states = states or ["loading", "empty", "error", "access_denied", "content_available"]
    default_viewports = viewports or [
        {"name": "desktop", "width": 1280, "height": 800},
        {"name": "mobile", "width": 390, "height": 844},
    ]

    doc: dict[str, Any] = {
        "design_contract_id": design_contract_id,
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "design_mode": design_mode,
        "compiled_at": _now_iso(),
        "compiled_by": compiled_by,
        "design_reference_set_id": design_reference_set_id,
        "references": refs,
        "screens": _origin_bucket(screens or [], origin="explicitly_provided"),
        "routes": _origin_bucket(routes or [], origin="explicitly_provided"),
        "components": _origin_bucket(components or [], origin="explicitly_provided"),
        "structure": _origin_bucket(structure or {}, origin="explicitly_provided"),
        "mandatory_text": _origin_bucket(mandatory_text or [], origin="explicitly_provided"),
        "mandatory_elements": _origin_bucket(
            mandatory_elements or [], origin="explicitly_provided"
        ),
        "forbidden_elements": _origin_bucket(
            forbidden_elements or [], origin="explicitly_provided"
        ),
        "navigation": _origin_bucket(navigation or {}, origin="explicitly_provided"),
        "behaviors": _origin_bucket(behaviors or [], origin="explicitly_provided"),
        "states": _origin_bucket(default_states, origin="explicitly_provided"),
        "viewports": _origin_bucket(default_viewports, origin="explicitly_provided"),
        "breakpoints": _origin_bucket(breakpoints or [], origin="explicitly_provided"),
        "tokens": _origin_bucket(tokens or {}, origin="explicitly_provided"),
        "typography": _origin_bucket(typography or {}, origin="explicitly_provided"),
        "colors": _origin_bucket(colors or {}, origin="explicitly_provided"),
        "spacing": _origin_bucket(spacing or {}, origin="explicitly_provided"),
        "radii": _origin_bucket(radii or {}, origin="explicitly_provided"),
        "shadows": _origin_bucket(shadows or {}, origin="explicitly_provided"),
        "icons": _origin_bucket(icons or [], origin="explicitly_provided"),
        "assets": _origin_bucket(assets or [], origin="explicitly_provided"),
        "responsive_rules": _origin_bucket(
            responsive_rules or [], origin="explicitly_provided"
        ),
        "accessibility": _origin_bucket(
            accessibility or {"required": True}, origin="explicitly_provided"
        ),
        "motion": _origin_bucket(motion or {}, origin="explicitly_provided"),
        "conformance_level": conformance_level,
        "tolerances": _origin_bucket(default_tolerances, origin="explicitly_provided"),
        "free_zones": _origin_bucket(free_zones or [], origin="agent_freedom"),
        "human_decisions_required": human_decisions_required or [],
        "inferences": tagged_inferences,
        "design_system_precedence": design_system_precedence,
        "reference_validation_issues": issues,
        "status": "active",
    }
    doc["contract_hash"] = sha256_canonical(
        {k: v for k, v in doc.items() if k != "contract_hash"}
    )
    if persist:
        dump_yaml(path, doc)
    return doc


def load_design_contract(workspace: Workspace, design_contract_id: str) -> dict[str, Any]:
    path = contract_path(workspace, design_contract_id)
    if not path.is_file():
        raise DesignContractError(
            "not_found", f"design contract {design_contract_id!r} not found"
        )
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        raise DesignContractError("invalid_contract", "design contract must be an object")
    return doc


def unwrap(field: Any) -> Any:
    """Return raw value from a provenance-tagged contract field."""
    if isinstance(field, dict) and "value" in field and "origin" in field:
        return field["value"]
    return field
