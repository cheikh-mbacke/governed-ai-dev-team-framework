"""Version source-of-truth alignment tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_VERSION = REPO_ROOT / ".ai-team" / "framework-version.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"


def _framework_version() -> str:
    payload = json.loads(FRAMEWORK_VERSION.read_text(encoding="utf-8"))
    return str(payload["version"])


def _pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml version not found"
    return match.group(1)


def test_version_sources_are_aligned() -> None:
    framework = _framework_version()
    pyproject = _pyproject_version()
    readme = README.read_text(encoding="utf-8")
    assert framework == pyproject, f"framework-version.json ({framework}) != pyproject.toml ({pyproject})"
    assert framework in readme, f"README.md does not mention framework version {framework}"
