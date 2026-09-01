"""Cursor adapter compatibility negotiation (Document 12 §4, CT-008, CT-009)."""

from __future__ import annotations

from typing import Any

from governed_ai.contracts.compatibility import CompatibilityReport
from governed_ai.contracts.semver import version_in_range
from governed_ai.adapters.spi import (
    AdapterDescriptor,
    ProcedureRevision,
    PublishedContractBundle,
    RoleDefinitionRevision,
)

UNSUPPORTED_CONTRACT = "UNSUPPORTED_CONTRACT"
CAPABILITY_NOT_ENFORCEABLE = "CAPABILITY_NOT_ENFORCEABLE"


def _normalize_platform(platform: str) -> tuple[str, bool]:
    if platform in {"windows-native", "windows"}:
        return "windows", platform == "windows-native"
    return platform, False


def negotiate_compatibility(
    descriptor: AdapterDescriptor,
    bundle: PublishedContractBundle,
    role: RoleDefinitionRevision,
    procedure: ProcedureRevision,
    platform: str,
    *,
    protocol_version: str = "1.0",
) -> CompatibilityReport:
    """Return a CompatibilityReport; CT-008/009 semantics encoded in issues."""
    _ = procedure
    issues: list[dict[str, Any]] = []
    compatible = True

    if protocol_version not in descriptor["protocol_versions"]:
        issues.append(
            {
                "code": UNSUPPORTED_CONTRACT,
                "path": "protocol_version",
                "required": protocol_version,
                "available": ",".join(descriptor["protocol_versions"]),
            }
        )
        compatible = False

    normalized_platform, is_windows_native = _normalize_platform(platform)
    if normalized_platform not in descriptor["platforms"]:
        issues.append(
            {
                "code": UNSUPPORTED_CONTRACT,
                "path": "platform",
                "required": platform,
                "available": ",".join(descriptor["platforms"]),
            }
        )
        compatible = False

    bundle_version = str(bundle.get("bundle_version", ""))
    if not version_in_range(bundle_version, str(descriptor["bundle_version_range"])):
        issues.append(
            {
                "code": UNSUPPORTED_CONTRACT,
                "path": "bundle_version",
                "required": bundle_version,
                "available": str(descriptor["bundle_version_range"]),
            }
        )
        compatible = False

    product_level = str(role.get("writes", {}).get("product", {}).get("level", "none"))
    shell = str(role.get("capabilities", {}).get("shell", "deny"))
    network = str(role.get("capabilities", {}).get("network", "deny_by_default"))
    isolation = str(role.get("isolation", "not_required"))
    signal_commands = list(
        role.get("writes", {}).get("non_authoritative_signal_commands") or []
    )

    if shell == "scoped" and str(descriptor["capabilities"].get("per_role_product_scope")) == "partial":
        issues.append(
            {
                "code": CAPABILITY_NOT_ENFORCEABLE,
                "path": "capabilities.shell",
                "required": "scoped shell enforcement",
                "available": "partial hook-based enforcement",
                "fallback": "accept partial enforcement",
            }
        )

    if isolation == "required_for_concurrent_product_write" and is_windows_native:
        issues.append(
            {
                "code": CAPABILITY_NOT_ENFORCEABLE,
                "path": "isolation",
                "required": isolation,
                "available": "concurrent worktree isolation not guaranteed on windows-native",
                "fallback": "serialize product writers",
            }
        )

    if product_level == "none" and is_windows_native:
        if "RecordObservation" in signal_commands:
            issues.append(
                {
                    "code": CAPABILITY_NOT_ENFORCEABLE,
                    "path": "writes.product.level",
                    "required": "enforceable readonly sandbox",
                    "available": "workspace_readonly unavailable on native Windows",
                    "fallback": "mediated RecordObservation via Command Gateway",
                }
            )
        else:
            issues.append(
                {
                    "code": CAPABILITY_NOT_ENFORCEABLE,
                    "path": "writes.product.level",
                    "required": "enforceable readonly sandbox",
                    "available": "workspace_readonly unavailable on native Windows",
                }
            )
            compatible = False

    if network not in ("deny_by_default", "scoped"):
        issues.append(
            {
                "code": CAPABILITY_NOT_ENFORCEABLE,
                "path": "capabilities.network",
                "required": network,
                "available": "deny_by_default or scoped",
            }
        )
        compatible = False

    return CompatibilityReport(
        compatible=compatible,
        adapter_id=str(descriptor["adapter_id"]),
        role_id=str(role.get("role_id", "")),
        procedure_id=str(procedure.get("procedure_id", "")),
        issues=issues,
    )


def requires_blocking(report: CompatibilityReport) -> bool:
    return not report["compatible"]


def primary_issue_code(report: CompatibilityReport) -> str | None:
    issues = report.get("issues") or []
    if not issues:
        return None
    return str(issues[0].get("code", ""))
