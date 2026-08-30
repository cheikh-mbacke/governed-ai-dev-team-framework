"""Pre-write collision detection for install and update."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from distribution.installer.constants import FRAMEWORK_INSTALL_MARKERS
from distribution.installer.record import INSTALLATION_RECORD_FILE, normalize_path
from distribution.installer.hashes import sha256_file


@dataclass(frozen=True)
class Collision:
    path: str
    reason: str
    kind: str = "path_exists"


def _has_prior_install_record(target: Path) -> bool:
    """True only when there is actual evidence of a prior legitimate install.

    Fresh installs must never assume a path is framework-owned just because
    it has a familiar name (.cursor/, scripts/ai-team/, project-profile.yaml,
    ...) — a target with no installation-record.json has, by definition, no
    proven framework install, so any pre-existing content there is a real
    collision, not framework output to be silently replaced.
    """
    return (target / INSTALLATION_RECORD_FILE).is_file()


def _is_framework_marker(path: Path, target: Path) -> bool:
    if not _has_prior_install_record(target):
        return False
    try:
        rel = path.relative_to(target).as_posix()
    except ValueError:
        return False
    if rel in FRAMEWORK_INSTALL_MARKERS:
        return True
    if rel.startswith(".ai-team/constitution/"):
        return True
    if rel.startswith(".ai-team/schemas/"):
        return True
    if rel.startswith(".ai-team/contracts/"):
        return True
    if rel.startswith(".ai-team/templates/"):
        return True
    if rel.startswith(".ai-team/runtime/governed_ai/"):
        return True
    if rel.startswith(".cursor/"):
        return True
    if rel.startswith("scripts/ai-team/"):
        return True
    return False


# Files that only exist under a genuine pre-0.7.0 framework install. Their
# presence — not the mere existence of generic src/docs/adapters
# directories the new layout no longer touches — is what should steer an
# operator toward --update instead of a fresh install.
LEGACY_FRAMEWORK_FINGERPRINTS = frozenset(
    {
        "src/governed_ai/__init__.py",
        "adapters/cursor/manifest.json",
    }
)


def _legacy_framework_install_fingerprint(target: Path) -> str | None:
    for fingerprint in sorted(LEGACY_FRAMEWORK_FINGERPRINTS):
        if (target / fingerprint).is_file():
            return fingerprint
    return None


def scan_fresh_install_collisions(
    target: Path,
    destinations: list[Path],
    *,
    merge_agents: bool = True,
) -> list[Collision]:
    collisions: list[Collision] = []
    seen: set[str] = set()

    fingerprint = _legacy_framework_install_fingerprint(target)
    if fingerprint is not None:
        collisions.append(
            Collision(
                path=fingerprint,
                reason=(
                    "target already has a pre-0.7.0 framework install (legacy layout); "
                    "use --update, not a fresh install"
                ),
                kind="legacy_install_detected",
            )
        )

    for dest in destinations:
        rel = normalize_path(dest.relative_to(target))
        if rel in seen:
            continue
        seen.add(rel)

        if rel == "AGENTS.md" and merge_agents:
            continue

        if not dest.exists():
            continue

        if _is_framework_marker(dest, target):
            continue

        if dest.is_file():
            collisions.append(
                Collision(
                    path=rel,
                    reason="file exists and is not a recognized framework installation artifact",
                    kind="file_exists",
                )
            )
        elif dest.is_dir():
            if rel == "scripts" and any(dest.rglob("*")):
                non_framework = [
                    p
                    for p in dest.rglob("*")
                    if p.is_file() and not _is_framework_marker(p, target)
                ]
                if non_framework:
                    collisions.append(
                        Collision(
                            path=rel,
                            reason="directory contains non-framework files",
                            kind="directory_exists",
                        )
                    )
    return collisions


def scan_local_drift_collisions(
    target: Path,
    entries: list,
    installed_hashes: dict[str, str],
) -> list[Collision]:
    """Detect managed files modified locally since last install (v3 hashes)."""
    collisions: list[Collision] = []
    for entry in entries:
        if entry.action not in {"update", "merge"}:
            continue
        rel = entry.relative.as_posix()
        if rel == "AGENTS.md":
            continue
        dest = entry.destination
        if not dest.is_file():
            continue
        recorded = installed_hashes.get(rel)
        if not recorded:
            continue
        current = sha256_file(dest)
        if current != recorded:
            collisions.append(
                Collision(
                    path=rel,
                    reason=(
                        "managed file was modified locally since last install "
                        f"(recorded {recorded}, current {current})"
                    ),
                    kind="local_drift",
                )
            )
    return collisions


def format_collision_report(collisions: list[Collision]) -> str:
    lines = ["Collision report:", "=" * 17]
    for item in collisions:
        lines.append(f"{item.kind.upper():18} {item.path}")
        lines.append(f"                   {item.reason}")
    lines.append(f"Summary: {len(collisions)} collision(s).")
    return "\n".join(lines)
