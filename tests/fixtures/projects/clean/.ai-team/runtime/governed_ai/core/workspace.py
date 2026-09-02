"""Project workspace paths without script-relative discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AI_TEAM_DIR_NAME = ".ai-team"
FABRIC_DIR_NAME = ".fabric"
PAYLOAD_AI_TEAM_REL = Path("distribution") / "payload" / ".ai-team"


@dataclass(frozen=True, slots=True)
class Workspace:
    """Resolved project root and derived governance paths."""

    root: Path

    @property
    def fabric(self) -> Path | None:
        path = self.root / FABRIC_DIR_NAME
        return path if path.is_dir() else None

    @property
    def profile_path(self) -> Path:
        fabric_profile = self.root / FABRIC_DIR_NAME / "project-profile.yaml"
        if fabric_profile.is_file():
            return fabric_profile
        return self.root / AI_TEAM_DIR_NAME / "project-profile.yaml"

    @property
    def ai_team(self) -> Path:
        """Governance payload tree: payload depot on fabrication, `.ai-team/` on clients."""
        if (self.root / FABRIC_DIR_NAME / "project-profile.yaml").is_file():
            payload = self.root / PAYLOAD_AI_TEAM_REL
            if payload.is_dir():
                return payload
        return self.root / AI_TEAM_DIR_NAME

    @classmethod
    def from_root(cls, root: Path | str) -> Workspace:
        return cls(root=Path(root).resolve())

    @classmethod
    def discover(cls, start: Path | str) -> Workspace:
        """Walk upward until a fabrication (``.fabric/``) or client (``.ai-team/``) root is found."""
        current = Path(start).resolve()
        if current.is_file():
            current = current.parent
        while True:
            if (current / FABRIC_DIR_NAME / "project-profile.yaml").is_file():
                return cls(root=current)
            if (current / AI_TEAM_DIR_NAME).is_dir():
                return cls(root=current)
            parent = current.parent
            if parent == current:
                msg = (
                    f"Could not find {FABRIC_DIR_NAME} or {AI_TEAM_DIR_NAME} "
                    f"directory walking up from {start}"
                )
                raise FileNotFoundError(msg)
            current = parent
