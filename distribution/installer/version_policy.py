"""Release compatibility matrix and update-path validation (Document 9 §2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _version_key(version: str) -> tuple[int, ...]:
    """Sortable tuple for a MAJOR.MINOR.PATCH version string."""
    return tuple(int(x) for x in version.split("."))


def _compare_versions(a: str, b: str) -> int:
    """Return -1 / 0 / 1 for a < b / a == b / a > b (MAJOR.MINOR.PATCH only)."""
    ta, tb = _version_key(a), _version_key(b)
    return 0 if ta == tb else (-1 if ta < tb else 1)

# Legacy/unversioned installs accepted until first explicit version is recorded.
SUPPORTED_UPDATE_FROM: frozenset[str | None] = frozenset(
    {None, "0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0"}
)


@dataclass(frozen=True)
class AdapterReleaseSpec:
    """Compatibility contract for one adapter shipped with a product release."""

    adapter_version: str
    bundle_version_range: str
    protocol_versions: frozenset[str]


@dataclass(frozen=True)
class ReleaseSpec:
    """Compatibility contract for one product release."""

    update_from: frozenset[str | None]
    adapters: dict[str, AdapterReleaseSpec]
    data_schema_minimums: dict[str, int]
    min_constitution_version: str


RELEASE_MATRIX: dict[str, ReleaseSpec] = {
    "0.6.0": ReleaseSpec(
        update_from=frozenset({None, "0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0"}),
        adapters={
            "cursor": AdapterReleaseSpec(
                adapter_version="0.6.0",
                bundle_version_range=">=1.0.0,<2.0.0",
                protocol_versions=frozenset({"1.0"}),
            ),
        },
        data_schema_minimums={
            "installation_record": 3,
            "mutable_aggregate": 2,
            "bundle_manifest": 1,
            "framework_version_manifest": 1,
        },
        min_constitution_version="1.0.0",
    ),
    "0.7.0": ReleaseSpec(
        update_from=SUPPORTED_UPDATE_FROM,
        adapters={
            "cursor": AdapterReleaseSpec(
                adapter_version="0.7.0",
                bundle_version_range=">=1.0.0,<2.0.0",
                protocol_versions=frozenset({"1.0"}),
            ),
        },
        data_schema_minimums={
            "installation_record": 3,
            "mutable_aggregate": 2,
            "bundle_manifest": 1,
            "framework_version_manifest": 1,
        },
        min_constitution_version="1.0.0",
    ),
}


def current_release_spec() -> ReleaseSpec:
    """Return the highest SemVer release entry declared in the matrix."""
    if not RELEASE_MATRIX:
        raise RuntimeError("RELEASE_MATRIX is empty")
    version = max(RELEASE_MATRIX, key=_semver_sort_key)
    return RELEASE_MATRIX[version]


def release_spec_for(version: str) -> ReleaseSpec | None:
    return RELEASE_MATRIX.get(version)


def _semver_sort_key(version: str) -> tuple[int, ...]:
    return _version_key(version)


def adapter_release_spec(product_version: str, adapter_id: str) -> AdapterReleaseSpec | None:
    spec = release_spec_for(product_version)
    if spec is None:
        return None
    return spec.adapters.get(adapter_id)


def validate_update_path(installed_version: str | None, new_version: str) -> None:
    """Reject unknown, unsupported, or downgrading update paths."""
    from distribution.installer.errors import InstallationValidationError

    spec = release_spec_for(new_version)
    if spec is None:
        raise InstallationValidationError(
            "UNKNOWN_RELEASE",
            f"No release compatibility matrix entry for {new_version!r}",
        )
    if (
        installed_version is not None
        and release_spec_for(installed_version) is not None
        and _compare_versions(new_version, installed_version) < 0
    ):
        raise InstallationValidationError(
            "DOWNGRADE_NOT_SUPPORTED",
            f"Downgrade from {installed_version!r} to {new_version!r} is not supported",
        )
    if installed_version not in spec.update_from:
        raise InstallationValidationError(
            "UNSUPPORTED_VERSION_PATH",
            f"No safe migration path from {installed_version!r} to {new_version}",
        )


def validate_adapter_descriptor_alignment(
    product_version: str,
    adapter_id: str,
    descriptor: dict[str, Any],
) -> list[str]:
    """Return human-readable errors when a descriptor drifts from the release matrix."""
    errors: list[str] = []
    expected = adapter_release_spec(product_version, adapter_id)
    if expected is None:
        return [f"no adapter release spec for {adapter_id!r} at product version {product_version!r}"]

    declared_version = str(descriptor.get("adapter_version", ""))
    if declared_version != expected.adapter_version:
        errors.append(
            f"{adapter_id} adapter_version {declared_version!r} must equal "
            f"product version {expected.adapter_version!r} for shipped adapters"
        )

    declared_range = str(descriptor.get("bundle_version_range", ""))
    if declared_range != expected.bundle_version_range:
        errors.append(
            f"{adapter_id} bundle_version_range {declared_range!r} must match "
            f"release matrix {expected.bundle_version_range!r}"
        )

    declared_protocols = {
        str(item) for item in (descriptor.get("protocol_versions") or []) if str(item)
    }
    if declared_protocols != set(expected.protocol_versions):
        errors.append(
            f"{adapter_id} protocol_versions {sorted(declared_protocols)!r} must match "
            f"release matrix {sorted(expected.protocol_versions)!r}"
        )
    return errors


def validate_release_matrix(root: Path) -> list[str]:
    """Ensure pyproject.toml product version is declared and current in RELEASE_MATRIX."""
    from distribution.installer.source_manifest import read_product_version

    errors: list[str] = []
    try:
        product_version = read_product_version(root)
    except (OSError, ValueError) as exc:
        return [f"cannot read product version: {exc}"]

    if not RELEASE_MATRIX:
        return ["RELEASE_MATRIX is empty"]

    latest_matrix_version = max(RELEASE_MATRIX, key=_semver_sort_key)

    if product_version not in RELEASE_MATRIX:
        errors.append(
            "pyproject.toml declares "
            f"{product_version!r} but RELEASE_MATRIX has no matching entry; "
            "add a ReleaseSpec in distribution/installer/version_policy.py"
        )
    elif _compare_versions(product_version, latest_matrix_version) < 0:
        errors.append(
            "pyproject.toml version "
            f"{product_version!r} is older than the newest RELEASE_MATRIX entry "
            f"{latest_matrix_version!r}; bump pyproject.toml or remove stale matrix entries"
        )
    elif _compare_versions(product_version, latest_matrix_version) > 0:
        errors.append(
            "pyproject.toml version "
            f"{product_version!r} is newer than the newest RELEASE_MATRIX entry "
            f"{latest_matrix_version!r}; add the release entry before publishing"
        )

    if product_version in RELEASE_MATRIX:
        spec = RELEASE_MATRIX[product_version]
        prior_versions = [
            version
            for version in RELEASE_MATRIX
            if version != product_version
            and _compare_versions(version, product_version) < 0
        ]
        if prior_versions:
            previous_release = max(prior_versions, key=_semver_sort_key)
            if previous_release not in spec.update_from:
                errors.append(
                    f"RELEASE_MATRIX[{product_version!r}].update_from must include "
                    f"previous release {previous_release!r}"
                )
        if product_version not in spec.update_from:
            errors.append(
                f"RELEASE_MATRIX[{product_version!r}].update_from must include "
                f"{product_version!r} for idempotent --update"
            )

    return errors


__all__ = [
    "AdapterReleaseSpec",
    "RELEASE_MATRIX",
    "ReleaseSpec",
    "SUPPORTED_UPDATE_FROM",
    "adapter_release_spec",
    "current_release_spec",
    "release_spec_for",
    "validate_adapter_descriptor_alignment",
    "validate_release_matrix",
    "validate_update_path",
]
