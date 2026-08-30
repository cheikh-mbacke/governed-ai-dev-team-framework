"""Adapter Service Provider Interface (Document 12 §3.2).

Structural typing via ``Protocol``; ``AdapterSPIBase`` offers an optional ABC for
explicit implementers. ``install_artifacts`` is defined in Document 12 but
out of scope for Phase 1 scaffolding (Distribution, Phase 5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Protocol, TypedDict, runtime_checkable

from governed_ai.contracts.compatibility import CompatibilityReport

RuntimeStatus = Literal["succeeded", "failed", "blocked", "cancelled", "timed_out"]


class AdapterCapabilities(TypedDict):
    """Capability flags declared by an adapter (Document 12 §3.1)."""

    per_role_readonly: bool
    per_role_product_scope: str
    mediated_core_commands: bool
    hooks: bool
    mcp: bool
    isolated_worktree: bool


class AdapterDescriptor(TypedDict):
    """Self-description returned by ``describe()`` (Document 12 §3.1)."""

    adapter_id: str
    adapter_version: str
    protocol_versions: list[str]
    bundle_version_range: str
    platforms: list[str]
    capabilities: AdapterCapabilities


class PublishedContractBundle(TypedDict):
    """Published bundle manifest reference (Document 12 §2.1)."""

    schema_version: int
    bundle_version: str
    created_at: str
    content_hash: str
    roles: list[str]
    procedures: list[str]


class RoleDefinitionRevision(TypedDict, total=False):
    """Role revision compiled from the bundle (Document 12 §2.2)."""

    role_id: str
    revision: str
    mandate: str
    writes: dict[str, object]
    capabilities: dict[str, object]
    approval_policy: dict[str, object]
    procedure_refs: list[dict[str, str]]
    model_preference: str
    isolation: str


class ProcedureRevision(TypedDict, total=False):
    """Procedure revision compiled from the bundle (Document 12 §2.3)."""

    procedure_id: str
    revision: str
    intent: str
    invocation_mode: str
    required_inputs: list[str]
    steps: list[str]
    required_outputs: list[str]
    invariants: list[str]


class ProjectProfile(TypedDict, total=False):
    """Project profile passed to ``compile()`` alongside the bundle."""

    project_id: str
    primary_language: str
    package_manager: str


class ArtifactEntry(TypedDict, total=False):
    """Single staged artifact produced by ``compile()``."""

    kind: str
    path: str
    sha256: str


class ArtifactManifest(TypedDict):
    """Manifest of artifacts written to staging by ``compile()``."""

    adapter_id: str
    adapter_version: str
    bundle_version: str
    artifacts: list[ArtifactEntry]


class AdapterIdentity(TypedDict):
    """Nested adapter identity on execution envelopes (Document 12 §5–§6)."""

    id: str
    version: str


class ExecutionContract(TypedDict):
    """Contract slice carried on execution envelopes."""

    bundle_version: str
    bundle_hash: str
    role_id: str
    role_revision: str
    procedure_id: str
    procedure_revision: str


class ExecutionRequest(TypedDict, total=False):
    """Input to ``execute()`` (Document 12 §5)."""

    protocol_version: str
    execution_id: str
    correlation_id: str
    adapter: AdapterIdentity
    contract: ExecutionContract
    project_id: str
    work_unit_id: str
    base_sha: str
    context_package_ref: str
    resolved_scope: list[str]
    approvals: list[object]
    requested_at: str
    execution_workspace: str
    work_unit_snapshot: dict[str, object]
    kill_switch_path: str
    allowed_shell_commands: list[str]
    allowed_paths: list[str]


class RuntimeCheck(TypedDict, total=False):
    """Check result embedded in ``RuntimeResult``."""

    name: str
    status: str
    evidence_ref: str | None


class RuntimeArtifact(TypedDict, total=False):
    """Artifact reference embedded in ``RuntimeResult``."""

    kind: str
    path: str
    sha256: str


class RuntimeWorkspace(TypedDict, total=False):
    """Workspace SHA references in ``RuntimeResult``."""

    base_sha: str
    result_sha: str


class RuntimeResultContract(TypedDict):
    """Contract slice on ``RuntimeResult`` (no bundle_hash)."""

    bundle_version: str
    role_id: str
    role_revision: str
    procedure_id: str
    procedure_revision: str


class RuntimeResult(TypedDict, total=False):
    """Output of ``execute()`` and ``collect()`` (Document 12 §6)."""

    protocol_version: str
    execution_id: str
    correlation_id: str
    status: RuntimeStatus
    started_at: str
    finished_at: str
    adapter: AdapterIdentity
    contract: RuntimeResultContract
    workspace: RuntimeWorkspace
    checks: list[RuntimeCheck]
    artifacts: list[RuntimeArtifact]
    summary: str
    limitations: list[str]
    requested_commands: list[object]
    usage: dict[str, object]


@runtime_checkable
class AdapterSPI(Protocol):
    """Structural interface for tool-specific adapters (Document 12 §3.2)."""

    def describe(self) -> AdapterDescriptor:
        """Return the adapter descriptor without side effects."""
        ...

    def check_compatibility(
        self,
        bundle: PublishedContractBundle,
        role: RoleDefinitionRevision,
        procedure: ProcedureRevision,
        platform: str,
    ) -> CompatibilityReport:
        """Negotiate compatibility before execution; no side effects."""
        ...

    def compile(
        self,
        bundle: PublishedContractBundle,
        project_profile: ProjectProfile,
    ) -> ArtifactManifest:
        """Compile bundle + profile into staged artifacts only."""
        ...

    def execute(self, request: ExecutionRequest) -> RuntimeResult:
        """Launch the native tool and return an operational result."""
        ...

    def collect(self, execution_id: str) -> RuntimeResult:
        """Read or resume a prior execution by id."""
        ...


class AdapterSPIBase(ABC):
    """Optional explicit base class for adapter implementations."""

    @abstractmethod
    def describe(self) -> AdapterDescriptor:
        raise NotImplementedError

    @abstractmethod
    def check_compatibility(
        self,
        bundle: PublishedContractBundle,
        role: RoleDefinitionRevision,
        procedure: ProcedureRevision,
        platform: str,
    ) -> CompatibilityReport:
        raise NotImplementedError

    @abstractmethod
    def compile(
        self,
        bundle: PublishedContractBundle,
        project_profile: ProjectProfile,
    ) -> ArtifactManifest:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> RuntimeResult:
        raise NotImplementedError

    @abstractmethod
    def collect(self, execution_id: str) -> RuntimeResult:
        raise NotImplementedError


__all__ = [
    "AdapterCapabilities",
    "AdapterDescriptor",
    "AdapterIdentity",
    "AdapterSPI",
    "AdapterSPIBase",
    "ArtifactEntry",
    "ArtifactManifest",
    "CompatibilityReport",
    "ExecutionContract",
    "ExecutionRequest",
    "ProcedureRevision",
    "ProjectProfile",
    "PublishedContractBundle",
    "RoleDefinitionRevision",
    "RuntimeArtifact",
    "RuntimeCheck",
    "RuntimeResult",
    "RuntimeResultContract",
    "RuntimeStatus",
    "RuntimeWorkspace",
]
