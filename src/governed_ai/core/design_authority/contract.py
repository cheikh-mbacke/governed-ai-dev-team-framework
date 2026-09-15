"""Design Contract compiler — versioned, provenance-aware visual obligations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import (
    DESIGN_MODES,
    INFORMATION_ORIGINS,
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
    source_refs: list[Any] | None = None,
    authority_level: str | None = None,
    validated_by: str | None = None,
    validated_at: str | None = None,
    authorization_id: str | None = None,
) -> dict[str, Any]:
    if origin not in INFORMATION_ORIGINS:
        raise DesignContractError(
            "invalid_information_origin",
            f"unknown information origin {origin!r}",
        )
    if authority_level is None:
        authority_level = (
            "authoritative"
            if origin in {"explicitly_provided", "human_decision", "inference_validated"}
            else "advisory"
        )
    bucket: dict[str, Any] = {
        "value": value,
        "origin": origin,
        "source_refs": list(source_refs or []),
        "authority_level": authority_level,
        "validated_by": validated_by,
        "validated_at": validated_at,
    }
    if authorization_id:
        bucket["authorization_id"] = authorization_id
    return bucket


def _provided_bucket(
    provided: Any | None,
    *,
    default: Any,
    default_origin: str = "compiler_default",
    provided_origin: str = "inference_proposed",
) -> dict[str, Any]:
    """Caller-supplied values are inference_proposed until human-validated."""
    if provided is not None:
        return _origin_bucket(provided, origin=provided_origin)
    return _origin_bucket(default, origin=default_origin)


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

    tagged_inferences = []
    for item in inferences or []:
        validated_by = str(item.get("validated_by") or "").strip()
        auth_id = item.get("authorization_id")
        # Never trust validated_by_human alone — require human: actor + authorization.
        if validated_by.startswith("human:") and auth_id:
            origin = "inference_validated"
            authoritative = True
        else:
            origin = "inference_proposed"
            authoritative = False
        tagged_inferences.append(
            {
                **{k: v for k, v in item.items() if k != "validated_by_human"},
                "origin": origin,
                "authoritative": authoritative,
                "validated_by": validated_by or None,
                "authorization_id": auth_id,
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
    if tolerances is not None:
        merged_tolerances = dict(default_tolerances)
        merged_tolerances.update(tolerances)
        tolerances_bucket = _origin_bucket(merged_tolerances, origin="inference_proposed")
    else:
        tolerances_bucket = _origin_bucket(default_tolerances, origin="compiler_default")

    default_states = ["loading", "empty", "error", "access_denied", "content_available"]
    default_viewports = [
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
        "screens": _provided_bucket(screens, default=[]),
        "routes": _provided_bucket(routes, default=[]),
        "components": _provided_bucket(components, default=[]),
        "structure": _provided_bucket(structure, default={}),
        "mandatory_text": _provided_bucket(mandatory_text, default=[]),
        "mandatory_elements": _provided_bucket(mandatory_elements, default=[]),
        "forbidden_elements": _provided_bucket(forbidden_elements, default=[]),
        "navigation": _provided_bucket(navigation, default={}),
        "behaviors": _provided_bucket(behaviors, default=[]),
        "states": _provided_bucket(states, default=default_states),
        "viewports": _provided_bucket(viewports, default=default_viewports),
        "breakpoints": _provided_bucket(breakpoints, default=[]),
        "tokens": _provided_bucket(tokens, default={}),
        "typography": _provided_bucket(typography, default={}),
        "colors": _provided_bucket(colors, default={}),
        "spacing": _provided_bucket(spacing, default={}),
        "radii": _provided_bucket(radii, default={}),
        "shadows": _provided_bucket(shadows, default={}),
        "icons": _provided_bucket(icons, default=[]),
        "assets": _provided_bucket(assets, default=[]),
        "responsive_rules": _provided_bucket(responsive_rules, default=[]),
        "accessibility": _provided_bucket(
            accessibility, default={"required": True}
        ),
        "motion": _provided_bucket(motion, default={}),
        "conformance_level": conformance_level,
        "tolerances": tolerances_bucket,
        "free_zones": _provided_bucket(free_zones, default=[]),
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
