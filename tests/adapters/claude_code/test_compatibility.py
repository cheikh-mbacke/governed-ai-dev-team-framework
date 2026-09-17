"""Claude Code compatibility negotiation — platform normalization."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.claude_code.compatibility import (
    UNSUPPORTED_CONTRACT,
    _normalize_platform,
    negotiate_compatibility,
)

from governed_ai.adapters.spi import (
    AdapterDescriptor,
    ProcedureRevision,
    PublishedContractBundle,
    RoleDefinitionRevision,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads(
    (REPO_ROOT / "adapters" / "claude_code" / "manifest.json").read_text(encoding="utf-8")
)
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"


def _descriptor() -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id=str(MANIFEST["adapter_id"]),
        adapter_version=str(MANIFEST["adapter_version"]),
        protocol_versions=list(MANIFEST["protocol_versions"]),
        bundle_version_range=str(MANIFEST["bundle_version_range"]),
        platforms=list(MANIFEST["platforms"]),
        capabilities=dict(MANIFEST["capabilities"]),
    )


def _bundle() -> PublishedContractBundle:
    data = json.loads((BUNDLE_V1 / "manifest.json").read_text(encoding="utf-8"))
    return PublishedContractBundle(
        schema_version=int(data["schema_version"]),
        bundle_version=str(data["bundle_version"]),
        created_at=str(data["created_at"]),
        content_hash=str(data["content_hash"]),
        roles=list(data["roles"]),
        procedures=list(data["procedures"]),
    )


def _role(role_id: str = "backend-developer") -> RoleDefinitionRevision:
    data = json.loads((BUNDLE_V1 / "roles" / f"{role_id}.json").read_text(encoding="utf-8"))
    return RoleDefinitionRevision(**data)


def _procedure(procedure_id: str = "implement-work-unit") -> ProcedureRevision:
    data = json.loads(
        (BUNDLE_V1 / "procedures" / f"{procedure_id}.json").read_text(encoding="utf-8")
    )
    return ProcedureRevision(**data)


def test_normalize_platform_maps_wsl_to_linux() -> None:
    assert _normalize_platform("wsl") == "linux"


def test_normalize_platform_keeps_windows_native_and_windows_equivalent() -> None:
    assert _normalize_platform("windows-native") == "windows"
    assert _normalize_platform("windows") == "windows"
    assert _normalize_platform("linux") == "linux"


def test_wsl_is_compatible_like_linux() -> None:
    report = negotiate_compatibility(
        _descriptor(),
        _bundle(),
        _role(),
        _procedure(),
        "wsl",
    )
    assert report["compatible"] is True
    assert not any(
        issue.get("path") == "platform" for issue in report.get("issues") or []
    )


def test_unknown_platform_still_rejected() -> None:
    report = negotiate_compatibility(
        _descriptor(),
        _bundle(),
        _role(),
        _procedure(),
        "freebsd",
    )
    assert report["compatible"] is False
    assert any(
        issue.get("path") == "platform" and issue.get("code") == UNSUPPORTED_CONTRACT
        for issue in report.get("issues") or []
    )


def test_backend_developer_scoped_shell_reports_partial_enforcement() -> None:
    """Unlike Cursor, Claude Code's readonly boundary (tools list) is a
    verified hard boundary on every platform — so this pilot's only
    CAPABILITY_NOT_ENFORCEABLE case is path-level scoped-write enforcement,
    not a platform-specific sandbox gap."""
    report = negotiate_compatibility(
        _descriptor(),
        _bundle(),
        _role("backend-developer"),
        _procedure("implement-work-unit"),
        "windows-native",
    )
    assert report["compatible"] is True
    codes = {issue.get("code") for issue in report.get("issues") or []}
    assert codes == {"CAPABILITY_NOT_ENFORCEABLE"}
