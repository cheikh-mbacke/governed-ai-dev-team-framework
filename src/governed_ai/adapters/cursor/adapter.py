"""Cursor Adapter SPI implementation."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.cursor.compatibility import (
    CAPABILITY_NOT_ENFORCEABLE,
    UNSUPPORTED_CONTRACT,
    negotiate_compatibility,
    primary_issue_code,
    requires_blocking,
)
from adapters.cursor.runtime.execute import collect_runtime_result, execute_runtime
from adapters.cursor.runtime.guard import (
    CapabilityNotEnforceableError,
    UnsupportedContractError,
    validate_requested_commands,
)
from adapters.cursor.runtime.checks import platform_profile

from governed_ai.adapters.cursor.compile import compile_manifest
from governed_ai.adapters.spi import (
    AdapterDescriptor,
    AdapterSPIBase,
    ArtifactManifest,
    CompatibilityReport,
    ExecutionRequest,
    ProcedureRevision,
    ProjectProfile,
    PublishedContractBundle,
    RoleDefinitionRevision,
    RuntimeResult,
)

_MANIFEST_PATH = Path(__file__).resolve().parents[4] / "adapters" / "cursor" / "manifest.json"


class CursorAdapter(AdapterSPIBase):
    """Cursor bundle compiler and runtime harness."""

    def __init__(
        self,
        *,
        project_root: Path,
        bundle_dir: Path | None = None,
        staging_dir: Path | None = None,
        templates_root: Path | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        self._bundle_dir = bundle_dir.resolve() if bundle_dir else None
        self._staging_dir = staging_dir.resolve() if staging_dir else None
        self._templates_root = templates_root.resolve() if templates_root else None

    def describe(self) -> AdapterDescriptor:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return AdapterDescriptor(
            adapter_id=str(data["adapter_id"]),
            adapter_version=str(data["adapter_version"]),
            protocol_versions=list(data["protocol_versions"]),
            bundle_version_range=str(data["bundle_version_range"]),
            platforms=list(data["platforms"]),
            capabilities=dict(data["capabilities"]),
        )

    def check_compatibility(
        self,
        bundle: PublishedContractBundle,
        role: RoleDefinitionRevision,
        procedure: ProcedureRevision,
        platform: str,
    ) -> CompatibilityReport:
        return negotiate_compatibility(
            self.describe(),
            bundle,
            role,
            procedure,
            platform,
            protocol_version="1.0",
        )

    def compile(
        self,
        bundle: PublishedContractBundle,
        project_profile: ProjectProfile,
    ) -> ArtifactManifest:
        if self._bundle_dir is None or self._staging_dir is None:
            raise RuntimeError("compile() requires bundle_dir and staging_dir")
        _ = bundle
        manifest = compile_manifest(
            self._bundle_dir,
            self._staging_dir,
            dict(project_profile),
            templates_root=self._templates_root,
        )
        return ArtifactManifest(
            adapter_id=str(manifest["adapter_id"]),
            adapter_version=str(manifest["adapter_version"]),
            bundle_version=str(manifest["bundle_version"]),
            artifacts=list(manifest["artifacts"]),
        )

    def execute(self, request: ExecutionRequest) -> RuntimeResult:
        descriptor = self.describe()
        protocol_version = str(request.get("protocol_version", "1.0"))
        if protocol_version not in descriptor["protocol_versions"]:
            raise UnsupportedContractError(
                UNSUPPORTED_CONTRACT,
                f"unsupported protocol_version: {protocol_version}",
            )

        contract = request["contract"]
        role = self._load_role(str(contract["role_id"]))
        procedure = self._load_procedure(str(contract["procedure_id"]))
        platform = str(request.get("platform") or platform_profile())
        bundle = self._load_bundle_manifest()

        report = negotiate_compatibility(
            descriptor,
            bundle,
            role,
            procedure,
            platform,
            protocol_version=protocol_version,
        )
        if requires_blocking(report):
            code = primary_issue_code(report) or UNSUPPORTED_CONTRACT
            message = f"compatibility blocked: {code}"
            if code == CAPABILITY_NOT_ENFORCEABLE:
                raise CapabilityNotEnforceableError(code, message)
            raise UnsupportedContractError(code, message)

        validate_requested_commands(request, role)
        execution_workspace = request.get("execution_workspace")
        project_root = (
            Path(str(execution_workspace)).resolve()
            if execution_workspace
            else self._project_root
        )
        return execute_runtime(project_root, request)

    def collect(self, execution_id: str) -> RuntimeResult:
        return collect_runtime_result(self._project_root, execution_id)

    def _load_bundle_manifest(self) -> PublishedContractBundle:
        if self._bundle_dir is None:
            raise RuntimeError("execute() requires bundle_dir for compatibility negotiation")
        data = json.loads((self._bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        return PublishedContractBundle(
            schema_version=int(data["schema_version"]),
            bundle_version=str(data["bundle_version"]),
            created_at=str(data["created_at"]),
            content_hash=str(data["content_hash"]),
            roles=list(data["roles"]),
            procedures=list(data["procedures"]),
        )

    def _load_role(self, role_id: str) -> RoleDefinitionRevision:
        if self._bundle_dir is None:
            raise RuntimeError(f"execute() requires bundle_dir to resolve role {role_id}")
        path = self._bundle_dir / "roles" / f"{role_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return RoleDefinitionRevision(**data)

    def _load_procedure(self, procedure_id: str) -> ProcedureRevision:
        if self._bundle_dir is None:
            raise RuntimeError(
                f"execute() requires bundle_dir to resolve procedure {procedure_id}"
            )
        path = self._bundle_dir / "procedures" / f"{procedure_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProcedureRevision(**data)
