"""Cursor Adapter SPI implementation."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.cursor.runtime.execute import collect_runtime_result, execute_runtime

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
        descriptor = self.describe()
        supported = platform in descriptor["platforms"]
        return CompatibilityReport(
            compatible=supported and bundle["bundle_version"].startswith("1."),
            adapter_id=descriptor["adapter_id"],
            role_id=str(role.get("role_id", "")),
            procedure_id=str(procedure.get("procedure_id", "")),
            issues=[] if supported else [{"code": "UNSUPPORTED_PLATFORM", "path": platform}],
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
        return execute_runtime(self._project_root, request)

    def collect(self, execution_id: str) -> RuntimeResult:
        return collect_runtime_result(self._project_root, execution_id)
