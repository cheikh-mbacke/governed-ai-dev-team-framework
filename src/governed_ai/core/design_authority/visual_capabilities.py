"""Visual adapter capability requirements for design-bound Work Units."""

from __future__ import annotations

from typing import Any


def visual_capability_defaults() -> dict[str, Any]:
    return {
        "visual_input": False,
        "visual_formats": [],
        "pdf": False,
        "svg": False,
        "figma_url": False,
        "screenshot": False,
        "browser_automation": False,
        "viewport_control": False,
        "dom_inspection": False,
        "visual_comparison": False,
    }


def merge_visual_capabilities(descriptor: dict[str, Any]) -> dict[str, Any]:
    merged = visual_capability_defaults()
    for key in merged:
        if key in descriptor:
            merged[key] = descriptor[key]
    nested = descriptor.get("visual") or {}
    if isinstance(nested, dict):
        for key, value in nested.items():
            if key in merged:
                merged[key] = value
    if descriptor.get("visual_input") is True:
        merged["visual_input"] = True
    return merged


def required_visual_capabilities_for_references(
    references: list[dict[str, Any]],
) -> dict[str, bool]:
    required = {
        "visual_input": False,
        "pdf": False,
        "svg": False,
        "figma_url": False,
        "screenshot": False,
    }
    for ref in references:
        authority = ref.get("authority_level")
        source_type = str(ref.get("source_type") or "")
        path = str(ref.get("source_path") or "")
        uri = str(ref.get("source_uri") or "")
        needs_vision = authority == "authoritative" or bool(path) or bool(uri)
        if not needs_vision:
            continue
        required["visual_input"] = True
        lower_path = path.lower()
        if source_type == "pdf" or lower_path.endswith(".pdf"):
            required["pdf"] = True
        if source_type == "svg" or lower_path.endswith(".svg"):
            required["svg"] = True
        if source_type in {"figma_link"} or "figma.com" in uri:
            required["figma_url"] = True
        if source_type in {"png", "jpg", "jpeg", "webp", "screenshot", "wireframe"} or any(
            lower_path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")
        ):
            required["screenshot"] = True
    return required


def assert_visual_capabilities(
    descriptor: dict[str, Any] | Any,
    *,
    references: list[dict[str, Any]],
) -> None:
    """Refuse dispatch when the adapter cannot actually read required visuals."""
    # Lazy import avoids circular import with CommandGateway ↔ supervisor.
    from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError

    caps = merge_visual_capabilities(dict(descriptor or {}))
    required = required_visual_capabilities_for_references(references)
    if not required.get("visual_input"):
        return
    if not caps.get("visual_input"):
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_visual_input_capability",
                message=(
                    "Work Unit requires visual design references but the adapter "
                    "cannot consume visual input"
                ),
                path="capabilities.visual_input",
                details={"required": required, "available": caps},
            )
        )
    missing: list[str] = []
    for key in ("pdf", "svg", "figma_url", "screenshot"):
        if required.get(key) and not caps.get(key):
            missing.append(key)
    if missing:
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_visual_input_capability",
                message=f"adapter missing visual formats: {', '.join(missing)}",
                path="capabilities.visual",
                details={"missing": missing, "required": required, "available": caps},
            )
        )
