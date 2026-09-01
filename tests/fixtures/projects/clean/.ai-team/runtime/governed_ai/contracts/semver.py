"""SemVer parsing and comparison (Document 12 §1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

RANGE_RE = re.compile(r"^>=([0-9.]+)(?:,<([0-9.]+))?$")


@dataclass(frozen=True, order=False)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()


def _split_identifiers(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split(".") if part)


def _compare_identifiers(left: Iterable[str], right: Iterable[str]) -> int:
    left_list = list(left)
    right_list = list(right)
    length = max(len(left_list), len(right_list))
    for index in range(length):
        left_part = left_list[index] if index < len(left_list) else None
        right_part = right_list[index] if index < len(right_list) else None
        if left_part is None:
            return -1
        if right_part is None:
            return 1
        left_is_num = left_part.isdigit()
        right_is_num = right_part.isdigit()
        if left_is_num and right_is_num:
            left_num = int(left_part)
            right_num = int(right_part)
            if left_num != right_num:
                return -1 if left_num < right_num else 1
            continue
        if left_is_num != right_is_num:
            return -1 if left_is_num else 1
        if left_part != right_part:
            return -1 if left_part < right_part else 1
    return 0


def parse_semver(version: str) -> SemVer:
    """Parse a SemVer string; raises ValueError when invalid."""
    match = SEMVER_RE.fullmatch(version.strip())
    if not match:
        raise ValueError(f"invalid SemVer: {version!r}")
    major, minor, patch, prerelease, build = match.groups()
    return SemVer(
        major=int(major),
        minor=int(minor),
        patch=int(patch),
        prerelease=_split_identifiers(prerelease) if prerelease else (),
        build=_split_identifiers(build) if build else (),
    )


def compare_semver(left: str | SemVer, right: str | SemVer) -> int:
    """Return -1 if left < right, 0 if equal, 1 if left > right."""
    left_parsed = left if isinstance(left, SemVer) else parse_semver(left)
    right_parsed = right if isinstance(right, SemVer) else parse_semver(right)
    if left_parsed.major != right_parsed.major:
        return -1 if left_parsed.major < right_parsed.major else 1
    if left_parsed.minor != right_parsed.minor:
        return -1 if left_parsed.minor < right_parsed.minor else 1
    if left_parsed.patch != right_parsed.patch:
        return -1 if left_parsed.patch < right_parsed.patch else 1
    if not left_parsed.prerelease and not right_parsed.prerelease:
        return 0
    if not left_parsed.prerelease:
        return 1
    if not right_parsed.prerelease:
        return -1
    return _compare_identifiers(left_parsed.prerelease, right_parsed.prerelease)


def version_in_range(version: str, spec: str) -> bool:
    """Return True when ``version`` satisfies a ``>=lower[,<upper)`` range."""
    match = RANGE_RE.fullmatch(spec.strip())
    if not match:
        raise ValueError(f"unsupported version range spec: {spec!r}")
    lower = match.group(1)
    upper = match.group(2)
    if compare_semver(version, lower) < 0:
        return False
    if upper is not None and compare_semver(version, upper) >= 0:
        return False
    return True


__all__ = [
    "SEMVER_RE",
    "SemVer",
    "compare_semver",
    "parse_semver",
    "version_in_range",
]
