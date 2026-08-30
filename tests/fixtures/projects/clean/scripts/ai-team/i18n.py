"""Minimal EN/FR label helper for this repo's own scripts' terminal output.

Scope, deliberately narrow: only the fixed structural text a script prints on
its own initiative (headers, labels, fixed guidance sentences) - never the
technical contract. YAML keys, enum values (status: in_progress), file paths,
Work Unit/event/finding IDs, and error text produced by third-party libraries
(PyYAML, jsonschema) always stay as-is, in every language. See
docs/OPERATOR_GUIDE.md "Language scope" for why this boundary exists: an
agent's generated prose already follows project-profile.yaml's
communication.language (see .ai-team/project-profile.yaml's own comment on
that field); this module extends the same signal to the handful of scripts
under scripts/ai-team/ that print directly to a human without going through
an agent at all.
"""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

FRENCH_MARKERS = {"français", "francais", "french", "fr", "fr-fr"}


def project_language(root: Path) -> str:
    """Read communication.language from .ai-team/project-profile.yaml.

    Defaults to "english" whenever the file, the field, or PyYAML itself is
    unavailable - never fail a script's normal operation over a label choice.
    """
    if yaml is None:
        return "english"
    profile_path = root / ".ai-team" / "project-profile.yaml"
    if not profile_path.exists():
        return "english"
    try:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return "english"
    language = (profile.get("communication") or {}).get("language")
    return language or "english"


def is_french(language: str) -> bool:
    return (language or "").strip().lower() in FRENCH_MARKERS


def t(language: str, en: str, fr: str) -> str:
    """Pick the English or French form of one fixed label/sentence."""
    return fr if is_french(language) else en
