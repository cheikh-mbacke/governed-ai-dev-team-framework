"""Adapter capability handshake — never infer capabilities from method presence."""

from __future__ import annotations

from typing import Any

from governed_ai.core.execution_gateway.contracts import SCHEMA_VERSION, CapabilityDescriptor
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError


def build_capability_descriptor(
    *,
    adapter_id: str,
    adapter_version: str,
    supported_protocol_versions: list[str],
    supported_roles: list[str],
    supported_procedures: list[str],
    isolated_workspace: bool,
    cancellation: bool,
    progress_events: bool,
    structured_output: bool,
    command_enforcement: bool,
    filesystem_enforcement: bool,
    maximum_parallelism: int = 1,
    visual_input: bool = False,
    visual_formats: list[str] | None = None,
    pdf: bool = False,
    svg: bool = False,
    figma_url: bool = False,
    screenshot: bool = False,
    browser_automation: bool = False,
    viewport_control: bool = False,
    dom_inspection: bool = False,
    visual_comparison: bool = False,
) -> CapabilityDescriptor:
    if type(maximum_parallelism) is not int or maximum_parallelism < 1:
        raise ExecutionGatewayError(
            StructuredError(
                code="invalid_type",
                message="maximum_parallelism must be a positive integer",
                path="capabilities.maximum_parallelism",
            )
        )
    return CapabilityDescriptor(
        schema_version=SCHEMA_VERSION,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        supported_protocol_versions=list(supported_protocol_versions),
        supported_roles=list(supported_roles),
        supported_procedures=list(supported_procedures),
        isolated_workspace=isolated_workspace,
        cancellation=cancellation,
        progress_events=progress_events,
        structured_output=structured_output,
        command_enforcement=command_enforcement,
        filesystem_enforcement=filesystem_enforcement,
        maximum_parallelism=maximum_parallelism,
        visual_input=visual_input,
        visual_formats=list(visual_formats or []),
        pdf=pdf,
        svg=svg,
        figma_url=figma_url,
        screenshot=screenshot,
        browser_automation=browser_automation,
        viewport_control=viewport_control,
        dom_inspection=dom_inspection,
        visual_comparison=visual_comparison,
    )


def assert_capabilities(
    descriptor: CapabilityDescriptor | dict[str, Any],
    *,
    role_id: str,
    procedure_id: str,
    require_isolated_workspace: bool = True,
    require_structured_output: bool = True,
    require_filesystem_enforcement: bool = False,
    protocol_version: str = "1.0",
) -> None:
    """Refuse dispatch when a required capability is missing."""
    if not descriptor.get("adapter_id"):
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_adapter_capability",
                message="CapabilityDescriptor.adapter_id is required",
                path="capabilities.adapter_id",
            )
        )
    versions = set(descriptor.get("supported_protocol_versions") or [])
    if protocol_version not in versions:
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_adapter_capability",
                message=f"adapter does not support protocol {protocol_version!r}",
                path="capabilities.supported_protocol_versions",
            )
        )
    roles = set(descriptor.get("supported_roles") or [])
    if role_id not in roles:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_role",
                message=f"adapter does not support role {role_id!r}",
                path="capabilities.supported_roles",
            )
        )
    procedures = set(descriptor.get("supported_procedures") or [])
    if procedure_id not in procedures:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_procedure",
                message=f"adapter does not support procedure {procedure_id!r}",
                path="capabilities.supported_procedures",
            )
        )
    if require_isolated_workspace and not descriptor.get("isolated_workspace"):
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_adapter_capability",
                message="isolated_workspace capability required",
                path="capabilities.isolated_workspace",
            )
        )
    if require_structured_output and not descriptor.get("structured_output"):
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_adapter_capability",
                message="structured_output capability required",
                path="capabilities.structured_output",
            )
        )
    if require_filesystem_enforcement and not descriptor.get("filesystem_enforcement"):
        raise ExecutionGatewayError(
            StructuredError(
                code="missing_adapter_capability",
                message="filesystem_enforcement capability required",
                path="capabilities.filesystem_enforcement",
            )
        )
