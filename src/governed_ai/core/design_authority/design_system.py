"""Design system inventory and conflict detection against mockups."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governed_ai.core.design_authority.hashing import sha256_canonical
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.paths import ensure_design_layout, inventory_path
from governed_ai.core.persistence.io import dump_yaml, load_yaml
from governed_ai.core.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DesignSystemError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


PRECEDENCE_RULES = frozenset(
    {
        "design_system_wins",
        "mockup_wins",
        "escalate_on_conflict",
    }
)


def empty_inventory() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "updated_at": _now_iso(),
        "components": [],
        "variants": [],
        "tokens": {},
        "patterns": [],
        "icons": [],
        "usage_rules": [],
        "deprecated_components": [],
        "source_paths": [],
        "documentation": {"storybook": None, "docs": []},
    }


def load_inventory(workspace: Workspace) -> dict[str, Any]:
    ensure_design_layout(workspace)
    path = inventory_path(workspace)
    if not path.is_file():
        return empty_inventory()
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        raise DesignSystemError("invalid_inventory", "design system inventory must be an object")
    return doc


def save_inventory(workspace: Workspace, inventory: dict[str, Any]) -> dict[str, Any]:
    ensure_design_layout(workspace)
    inventory = dict(inventory)
    inventory["updated_at"] = _now_iso()
    inventory["revision"] = int(inventory.get("revision") or 1)
    inventory["inventory_hash"] = sha256_canonical(
        {k: v for k, v in inventory.items() if k != "inventory_hash"}
    )
    dump_yaml(inventory_path(workspace), inventory)
    return inventory


def find_existing_component(
    inventory: dict[str, Any], *, name: str, role: str | None = None
) -> list[dict[str, Any]]:
    needle = name.strip().lower()
    matches: list[dict[str, Any]] = []
    for component in inventory.get("components") or []:
        if not isinstance(component, dict):
            continue
        cname = str(component.get("name") or "").lower()
        aliases = [str(a).lower() for a in (component.get("aliases") or [])]
        if needle == cname or needle in aliases:
            matches.append(component)
            continue
        if role and str(component.get("role") or "").lower() == role.lower():
            matches.append(component)
    return matches


def require_search_before_create(
    inventory: dict[str, Any], *, proposed_name: str
) -> dict[str, Any]:
    matches = find_existing_component(inventory, name=proposed_name)
    return {
        "searched": True,
        "proposed_name": proposed_name,
        "matches": matches,
        "may_create": len(matches) == 0,
        "code": "existing_component_found" if matches else "no_existing_component",
    }


def detect_design_system_conflict(
    *,
    inventory: dict[str, Any],
    mockup_requirements: dict[str, Any],
    precedence: str = "escalate_on_conflict",
) -> dict[str, Any]:
    """Return a structured conflict when mockup contradicts the design system."""
    if precedence not in PRECEDENCE_RULES:
        raise DesignSystemError(
            "invalid_precedence",
            f"unknown design_system_precedence {precedence!r}",
        )

    conflicts: list[dict[str, Any]] = []
    mockup_components = list(mockup_requirements.get("components") or [])
    inventory_names = {
        str(c.get("name") or "").lower()
        for c in (inventory.get("components") or [])
        if isinstance(c, dict)
    }
    deprecated = {
        str(c.get("name") or "").lower()
        for c in (inventory.get("deprecated_components") or [])
        if isinstance(c, dict)
    }

    for name in mockup_components:
        key = str(name).lower()
        if key in deprecated:
            conflicts.append(
                {
                    "kind": "deprecated_component_in_mockup",
                    "component": name,
                    "message": f"mockup uses deprecated component {name!r}",
                }
            )
        # Custom one-off names that ignore existing inventory tokens/components.
        tokens = inventory.get("tokens") or {}
        mockup_tokens = mockup_requirements.get("tokens") or {}
        for token_name, token_value in mockup_tokens.items():
            system_value = tokens.get(token_name)
            if system_value is not None and system_value != token_value:
                conflicts.append(
                    {
                        "kind": "token_mismatch",
                        "token": token_name,
                        "mockup_value": token_value,
                        "design_system_value": system_value,
                        "message": f"token {token_name!r} differs between mockup and design system",
                    }
                )

        if inventory_names and key not in inventory_names and mockup_requirements.get(
            "require_existing_components_only"
        ):
            conflicts.append(
                {
                    "kind": "unknown_component",
                    "component": name,
                    "message": f"component {name!r} is not in the design system inventory",
                }
            )

    if not conflicts:
        return {
            "has_conflict": False,
            "resolution": "none",
            "conflicts": [],
            "decision_required": False,
        }

    if precedence == "escalate_on_conflict":
        return {
            "has_conflict": True,
            "resolution": "product_decision_required",
            "conflicts": conflicts,
            "decision_required": True,
            "code": "design_system_conflict",
        }
    if precedence == "design_system_wins":
        return {
            "has_conflict": True,
            "resolution": "design_system_wins",
            "conflicts": conflicts,
            "decision_required": False,
            "code": "design_system_conflict",
        }
    return {
        "has_conflict": True,
        "resolution": "mockup_wins",
        "conflicts": conflicts,
        "decision_required": False,
        "code": "design_system_conflict",
    }
