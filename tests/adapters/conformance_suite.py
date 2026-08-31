"""Universal adapter conformance harness (Document 14 §9 AD-001–AD-010, CT-008/009)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Protocol

import yaml

from adapters.cursor.compiler.staging import resolve_under_staging, validate_pre_install
from adapters.cursor.runtime.guard import (
    CapabilityNotEnforceableError,
    ExecutionGuardError,
    UnsupportedContractError,
)
from adapters.cursor.runtime.results import validate_runtime_result
from governed_ai.adapters.spi import (
    AdapterSPI,
    ExecutionRequest,
    ProcedureRevision,
    ProjectProfile,
    PublishedContractBundle,
    RoleDefinitionRevision,
)
from tests.contracts.semantic_parity import ADAPTER_ONLY_AGENTS

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
ADAPTER_MANIFEST = REPO_ROOT / "adapters" / "cursor" / "manifest.json"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "cursor" / "templates"
DEFAULT_PROFILE: ProjectProfile = {
    "project_id": "conformance-test",
    "primary_language": "python",
    "package_manager": "pip",
}
BASE_SHA = "a" * 40


class AdapterFactory(Protocol):
    def __call__(
        self,
        project_root: Path,
        *,
        bundle_dir: Path | None = None,
        staging_dir: Path | None = None,
    ) -> AdapterSPI:
        ...


def load_bundle_manifest(bundle_dir: Path = BUNDLE_V1) -> PublishedContractBundle:
    data = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    return PublishedContractBundle(
        schema_version=int(data["schema_version"]),
        bundle_version=str(data["bundle_version"]),
        created_at=str(data["created_at"]),
        content_hash=str(data["content_hash"]),
        roles=list(data["roles"]),
        procedures=list(data["procedures"]),
    )


def load_role(role_id: str, bundle_dir: Path = BUNDLE_V1) -> RoleDefinitionRevision:
    data = json.loads((bundle_dir / "roles" / f"{role_id}.json").read_text(encoding="utf-8"))
    return RoleDefinitionRevision(**data)


def load_procedure(
    procedure_id: str,
    bundle_dir: Path = BUNDLE_V1,
) -> ProcedureRevision:
    data = json.loads(
        (bundle_dir / "procedures" / f"{procedure_id}.json").read_text(encoding="utf-8")
    )
    return ProcedureRevision(**data)


def write_minimal_project(root: Path, *, work_unit_id: str = "WU-CONF-TEST") -> None:
    ai = root / ".ai-team"
    (ai / "work-units").mkdir(parents=True)
    (ai / "events").mkdir(parents=True)
    (ai / "state").mkdir(parents=True)
    wu = {
        "id": work_unit_id,
        "title": "Conformance test",
        "objective": {"result": "test"},
        "scope": {"include": [], "exclude": []},
        "expected_behavior": "test",
        "acceptance_criteria": [],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {},
        "status": "in_progress",
        "revision": 1,
        "created_at": "2026-08-29T10:00:00+00:00",
        "updated_at": "2026-08-29T10:00:00+00:00",
    }
    (ai / "work-units" / f"{work_unit_id}.yaml").write_text(
        yaml.safe_dump(wu, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (ai / "state" / "project-state.yaml").write_text(
        "project_id: conformance-test\nphase: execution\n",
        encoding="utf-8",
    )


def business_state_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for folder in ("work-units", "events", "state", "decisions", "findings"):
        base = root / ".ai-team" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yaml")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def sample_execution_request(
    *,
    execution_id: str = "EXE-AD-TEST",
    role_id: str = "backend-developer",
    procedure_id: str = "implement-work-unit",
    protocol_version: str = "1.0",
    platform: str = "linux",
    requested_commands: list[dict[str, Any]] | None = None,
) -> ExecutionRequest:
    request = ExecutionRequest(
        protocol_version=protocol_version,
        execution_id=execution_id,
        correlation_id=f"COR-{execution_id}",
        adapter={"id": "cursor", "version": "0.5.0"},
        contract={
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": role_id,
            "role_revision": "1.0.0",
            "procedure_id": procedure_id,
            "procedure_revision": "1.0.0",
        },
        project_id="conformance-test",
        work_unit_id="WU-CONF-TEST",
        base_sha=BASE_SHA,
        context_package_ref="CTX-CONF",
        resolved_scope=["src/"],
        approvals=[],
        requested_at="2026-08-29T18:00:00+00:00",
        platform=platform,
    )
    if requested_commands is not None:
        request["requested_commands"] = requested_commands
    return request


def run_ad001_descriptor(adapter: AdapterSPI) -> None:
    expected = json.loads(ADAPTER_MANIFEST.read_text(encoding="utf-8"))
    descriptor = adapter.describe()
    assert descriptor["adapter_id"] == expected["adapter_id"]
    assert descriptor["adapter_version"] == expected["adapter_version"]
    assert descriptor["protocol_versions"] == expected["protocol_versions"]
    assert descriptor["bundle_version_range"] == expected["bundle_version_range"]
    assert descriptor["platforms"] == expected["platforms"]
    assert descriptor["capabilities"] == expected["capabilities"]


def run_ad002_compile(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
    *,
    bundle_dir: Path = BUNDLE_V1,
) -> None:
    staging = tmp_path / "staging"
    adapter = adapter_factory(
        tmp_path,
        bundle_dir=bundle_dir,
        staging_dir=staging,
    )
    bundle = load_bundle_manifest(bundle_dir)
    manifest = adapter.compile(bundle, DEFAULT_PROFILE)
    assert manifest["adapter_id"] == "cursor"
    assert manifest["bundle_version"] == "1.0.0"
    assert manifest["artifacts"]
    for entry in manifest["artifacts"]:
        rel = entry["path"]
        assert not Path(rel).is_absolute()
        target = resolve_under_staging(staging, rel)
        assert target.is_file()
        assert entry["sha256"].startswith("sha256:")
    validate_pre_install(staging, dict(manifest))


def run_ad003_deterministic_compile(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
    *,
    bundle_dir: Path = BUNDLE_V1,
) -> None:
    staging_a = tmp_path / "a"
    staging_b = tmp_path / "b"
    adapter_a = adapter_factory(tmp_path, bundle_dir=bundle_dir, staging_dir=staging_a)
    adapter_b = adapter_factory(tmp_path, bundle_dir=bundle_dir, staging_dir=staging_b)
    bundle = load_bundle_manifest(bundle_dir)
    manifest_a = adapter_a.compile(bundle, DEFAULT_PROFILE)
    manifest_b = adapter_b.compile(bundle, DEFAULT_PROFILE)
    assert manifest_a == manifest_b
    for entry in manifest_a["artifacts"]:
        rel = entry["path"]
        assert (staging_a / rel).read_bytes() == (staging_b / rel).read_bytes()


def run_ad004_restrictive_capability_available(adapter: AdapterSPI) -> None:
    bundle = load_bundle_manifest()
    role = load_role("backend-developer")
    procedure = load_procedure("implement-work-unit")
    report = adapter.check_compatibility(bundle, role, procedure, "linux")
    assert report["compatible"] is True
    codes = {issue.get("code") for issue in report.get("issues") or []}
    assert "CAPABILITY_NOT_ENFORCEABLE" in codes
    assert any(issue.get("fallback") for issue in report.get("issues") or [])


def write_blocked_network_bundle(root: Path) -> Path:
    bundle_dir = root / "blocked-bundle"
    bundle_dir.mkdir(parents=True)
    shutil.copytree(BUNDLE_V1 / "procedures", bundle_dir / "procedures")
    (bundle_dir / "roles").mkdir()
    role = dict(load_role("backend-developer"))
    role["role_id"] = "blocked-network"
    role["capabilities"] = dict(role["capabilities"])
    role["capabilities"]["network"] = "allow_all"
    (bundle_dir / "roles" / "blocked-network.json").write_text(
        json.dumps(role, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = dict(load_bundle_manifest())
    manifest["roles"] = ["roles/blocked-network.json"]
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle_dir


def run_ad005_impossible_capability_blocks(
    adapter: AdapterSPI,
    tmp_path: Path,
    adapter_factory: AdapterFactory,
) -> None:
    bundle = load_bundle_manifest()
    impossible_role = RoleDefinitionRevision(
        role_id="impossible-network",
        revision="1.0.0",
        writes={
            "product": {"level": "none", "paths": []},
            "authoritative_governance_commands": [],
            "non_authoritative_signal_commands": [],
        },
        capabilities={
            "repository_read": True,
            "shell": "deny",
            "network": "allow_all",
            "external_tools": [],
        },
        isolation="not_required",
    )
    procedure = load_procedure("audit-release")
    report = adapter.check_compatibility(bundle, impossible_role, procedure, "linux")
    assert report["compatible"] is False
    assert any(
        issue.get("code") == "CAPABILITY_NOT_ENFORCEABLE"
        for issue in report.get("issues") or []
    )

    write_minimal_project(tmp_path)
    blocked_bundle = write_blocked_network_bundle(tmp_path)
    runtime_adapter = adapter_factory(tmp_path, bundle_dir=blocked_bundle)
    request = sample_execution_request(
        execution_id="EXE-AD005",
        role_id="blocked-network",
        procedure_id="implement-work-unit",
    )
    with _expect_capability_block():
        runtime_adapter.execute(request)


def run_ad006_readonly_blocks_product_writes(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)
    request = sample_execution_request(
        execution_id="EXE-AD006",
        role_id="auditor",
        procedure_id="audit-release",
        requested_commands=[{"type": "CreateWorkUnit", "payload": {"id": "WU-FAKE"}}],
    )
    with _expect_guard("READONLY_PRODUCT_WRITE_FORBIDDEN"):
        adapter.execute(request)


def run_ad007_mediated_record_observation(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)

    blocked = sample_execution_request(
        execution_id="EXE-AD007-BLOCK",
        role_id="auditor",
        procedure_id="audit-release",
        platform="linux",
        requested_commands=[{"type": "RecordObservation", "payload": {"note": "x"}}],
    )
    with _expect_guard("UNMEDIATED_SIGNAL"):
        adapter.execute(blocked)

    allowed = sample_execution_request(
        execution_id="EXE-AD007-OK",
        role_id="auditor",
        procedure_id="audit-release",
        platform="linux",
        requested_commands=[
            {
                "type": "RecordObservation",
                "mediated": True,
                "payload": {"note": "observed gap"},
            }
        ],
    )
    before = business_state_digest(tmp_path)
    result = adapter.execute(allowed)
    after = business_state_digest(tmp_path)
    assert result["status"] == "blocked"
    assert before == after


def run_ad008_human_auth_required(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)
    request = sample_execution_request(
        execution_id="EXE-AD008",
        role_id="control-plane",
        procedure_id="orchestrator",
        requested_commands=[
            {"type": "RecordGateDecision", "payload": {"gate": "G1", "decision": "approve"}}
        ],
    )
    with _expect_guard("HUMAN_AUTH_REQUIRED"):
        adapter.execute(request)


def run_ad009_runtime_result_complete(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)
    request = sample_execution_request(execution_id="EXE-AD009")
    result = adapter.execute(request)
    assert result["execution_id"] == "EXE-AD009"
    assert result["adapter"]["id"] == "cursor"
    assert result["contract"]["role_id"] == "backend-developer"
    assert result["started_at"]
    assert result["finished_at"]
    assert result["artifacts"]
    assert result["artifacts"][0]["sha256"].startswith("sha256:")
    assert validate_runtime_result(dict(result)) == []


def run_ad010_agent_done_claim_leaves_core_unchanged(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)
    before = business_state_digest(tmp_path)
    request = sample_execution_request(execution_id="EXE-AD010")
    result = adapter.execute(request)
    after = business_state_digest(tmp_path)
    # A disabled/native-missing runtime may never fabricate a successful
    # completion claim. The authoritative Core state remains unchanged.
    assert result["status"] == "blocked"
    assert result.get("requested_commands") == []
    assert before == after


def run_ct008_unsupported_protocol_blocks_execution(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
) -> None:
    write_minimal_project(tmp_path)
    adapter = adapter_factory(tmp_path, bundle_dir=BUNDLE_V1)
    request = sample_execution_request(
        execution_id="EXE-CT008",
        protocol_version="2.0",
    )
    with _expect_unsupported_contract():
        adapter.execute(request)
    assert not (tmp_path / ".ai-team/runtime-results/EXE-CT008.json").exists()


def run_ct009_capability_not_enforceable_reported(adapter: AdapterSPI) -> None:
    bundle = load_bundle_manifest()
    role = RoleDefinitionRevision(
        role_id="network-unbounded",
        revision="1.0.0",
        writes={
            "product": {"level": "none", "paths": []},
            "authoritative_governance_commands": [],
            "non_authoritative_signal_commands": [],
        },
        capabilities={
            "repository_read": True,
            "shell": "deny",
            "network": "allow_all",
            "external_tools": [],
        },
        isolation="not_required",
    )
    procedure = load_procedure("audit-release")
    report = adapter.check_compatibility(bundle, role, procedure, "linux")
    assert any(
        issue.get("code") == "CAPABILITY_NOT_ENFORCEABLE"
        for issue in report.get("issues") or []
    )


def run_auth_smoke_adapter_only(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
    *,
    bundle_dir: Path = BUNDLE_V1,
) -> None:
    bundle = load_bundle_manifest(bundle_dir)
    role_ids = {Path(path).stem for path in bundle["roles"]}
    procedure_ids = {Path(path).stem for path in bundle["procedures"]}
    assert ADAPTER_ONLY_AGENTS.isdisjoint(role_ids)
    assert ADAPTER_ONLY_AGENTS.isdisjoint(procedure_ids)

    staging = tmp_path / "staging"
    adapter = adapter_factory(tmp_path, bundle_dir=bundle_dir, staging_dir=staging)
    manifest = adapter.compile(bundle, DEFAULT_PROFILE)
    paths = {entry["path"] for entry in manifest["artifacts"]}
    assert ".cursor/agents/auth-smoke.md" in paths
    auth_smoke = (staging / ".cursor/agents/auth-smoke.md").read_text(encoding="utf-8")
    assert "name: auth-smoke" in auth_smoke


class _ExpectContext:
    def __init__(self, exc_type: type[Exception], code: str | None = None) -> None:
        self.exc_type = exc_type
        self.code = code
        self.exc: Exception | None = None

    def __enter__(self) -> _ExpectContext:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object) -> bool:
        if exc_type is None:
            raise AssertionError(f"expected {self.exc_type.__name__}")
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.code is not None and getattr(exc, "code", None) != self.code:
            raise AssertionError(f"expected code {self.code}, got {getattr(exc, 'code', None)}")
        self.exc = exc  # type: ignore[assignment]
        return True


def _expect_unsupported_contract() -> _ExpectContext:
    return _ExpectContext(UnsupportedContractError, "UNSUPPORTED_CONTRACT")


def _expect_capability_block() -> _ExpectContext:
    return _ExpectContext(CapabilityNotEnforceableError, "CAPABILITY_NOT_ENFORCEABLE")


def _expect_guard(code: str) -> _ExpectContext:
    return _ExpectContext(ExecutionGuardError, code)


def run_full_conformance(
    adapter_factory: AdapterFactory,
    tmp_path: Path,
    *,
    bundle_dir: Path = BUNDLE_V1,
) -> None:
    probe = adapter_factory(tmp_path, bundle_dir=bundle_dir)
    run_ad001_descriptor(probe)
    run_ad002_compile(adapter_factory, tmp_path, bundle_dir=bundle_dir)
    run_ad003_deterministic_compile(adapter_factory, tmp_path, bundle_dir=bundle_dir)
    run_ad004_restrictive_capability_available(probe)
    run_ad005_impossible_capability_blocks(probe, tmp_path / "ad005", adapter_factory)
    run_ad006_readonly_blocks_product_writes(adapter_factory, tmp_path / "ad006")
    run_ad007_mediated_record_observation(adapter_factory, tmp_path / "ad007")
    run_ad008_human_auth_required(adapter_factory, tmp_path / "ad008")
    run_ad009_runtime_result_complete(adapter_factory, tmp_path / "ad009")
    run_ad010_agent_done_claim_leaves_core_unchanged(adapter_factory, tmp_path / "ad010")
    run_ct008_unsupported_protocol_blocks_execution(adapter_factory, tmp_path / "ct008")
    run_ct009_capability_not_enforceable_reported(probe)
    run_auth_smoke_adapter_only(adapter_factory, tmp_path / "auth", bundle_dir=bundle_dir)
