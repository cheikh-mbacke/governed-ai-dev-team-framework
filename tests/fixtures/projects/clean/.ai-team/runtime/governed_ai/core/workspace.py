"""Project workspace paths without script-relative discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AI_TEAM_DIR_NAME = ".ai-team"


@dataclass(frozen=True, slots=True)
class Workspace:
    """Resolved project root and derived governance paths."""

    root: Path

    @property
    def ai_team(self) -> Path:
        return self.root / AI_TEAM_DIR_NAME

    @classmethod
    def from_root(cls, root: Path | str) -> Workspace:
        return cls(root=Path(root).resolve())

    @classmethod
    def discover(cls, start: Path | str) -> Workspace:
        """Walk upward from *start* until a directory containing `.ai-team` is found."""
        current = Path(start).resolve()
        if current.is_file():
            current = current.parent
        while True:
            if (current / AI_TEAM_DIR_NAME).is_dir():
                return cls(root=current)
            parent = current.parent
            if parent == current:
                msg = f"Could not find {AI_TEAM_DIR_NAME} directory walking up from {start}"
                raise FileNotFoundError(msg)
            current = parent
