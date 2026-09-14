"""Canonical execution contract structures (schema_version 1).

Compatibility: additive fields may appear in later versions; unknown fields are
ignored by validators. Required fields below must always be present.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

SCHEMA_VERSION = 1
MAX_SUMMARY_CHARS = 8000
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_ARTIFACTS = 64
MAX_CHECKS = 128
MAX_LIMITATIONS = 64

TrustLevel = Literal[
    "agent_reported",
    "framework_observed",
    "framework_verified",
    "human_verified",
]

ExecutionStatus = Literal[
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "timed_out",
    "rejected",
]


class StructuredErrorDict(TypedDict, total=False):
    code: str
    message: str
    path: str
    details: dict[str, Any]


class CheckResult(TypedDict, total=False):
    schema_version: int
    canonical_id: str
    reported_name: str
    status: str
    blocking: bool
    trust_level: TrustLevel
    evidence_ref: str | None
    evidence_id: str | None
    verifier: str | None
    exit_code: int | None
    duration_ms: int | None
    transcript_hash: str | None
    limitations: list[str]


class ArtifactEvidence(TypedDict, total=False):
    schema_version: int
    kind: str
    path: str
    agent_reported_sha256: str | None
    observed_sha256: str | None
    trust_level: TrustLevel
    size_bytes: int | None


class WorkspaceResult(TypedDict, total=False):
    schema_version: int
    base_sha: str
    claimed_result_sha: str | None
    observed_head_sha: str | None
    promoted_sha: str | None
    trust_level: TrustLevel
    resumable: bool


class CapabilityDescriptor(TypedDict, total=False):
    schema_version: int
    adapter_id: str
    adapter_version: str
    supported_protocol_versions: list[str]
    supported_roles: list[str]
    supported_procedures: list[str]
    isolated_workspace: bool
    cancellation: bool
    progress_events: bool
    structured_output: bool
    command_enforcement: bool
    filesystem_enforcement: bool
    maximum_parallelism: int
    # Visual / multimodal design reference consumption (Design Authority).
    visual_input: bool
    visual_formats: list[str]
    pdf: bool
    svg: bool
    figma_url: bool
    screenshot: bool
    browser_automation: bool
    viewport_control: bool
    dom_inspection: bool
    visual_comparison: bool
    visual: dict[str, Any]


class ExecutionContract(TypedDict, total=False):
    schema_version: int
    contract_id: str
    bundle_version: str
    bundle_hash: str
    role_id: str
    role_revision: str
    procedure_id: str
    procedure_revision: str
    effective_scope: list[str]
    excluded_paths: list[str]
    required_checks: list[str]
    allowed_shell_commands: list[str]
    accessible_secrets: list[str]
    context_package_hash: str
    timeout_seconds: float
    max_artifact_bytes: int


class ExecutionRequest(TypedDict, total=False):
    schema_version: int
    execution_id: str
    run_id: str
    work_unit_id: str
    lease_id: str
    epoch: int
    role_id: str
    procedure_id: str
    base_sha: str
    context_package_ref: str
    context_package_hash: str
    contract: ExecutionContract
    adapter_id: str
    requested_at: str
    correlation_id: str


class ExecutionResult(TypedDict, total=False):
    schema_version: int
    execution_id: str
    run_id: str
    work_unit_id: str
    lease_id: str
    epoch: int
    role_id: str
    procedure_id: str
    status: ExecutionStatus
    summary: str
    checks: list[CheckResult]
    artifacts: list[ArtifactEvidence]
    requested_commands: list[object]
    limitations: list[str]
    workspace: WorkspaceResult
    usage: dict[str, Any]
    provider_metadata: dict[str, Any]
    context_package_hash: str
    errors: list[StructuredErrorDict]
