"""Version source-of-truth alignment tests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FRAMEWORK_VERSION = REPO_ROOT / ".fabric" / "framework-version.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"
ADAPTER_MANIFEST = REPO_ROOT / "adapters" / "cursor" / "manifest.json"


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


def test_adapter_manifest_tracks_product_version() -> None:
    product_version = _pyproject_version()
    descriptor = json.loads(ADAPTER_MANIFEST.read_text(encoding="utf-8"))
    from distribution.installer.version_policy import validate_adapter_descriptor_alignment

    assert validate_adapter_descriptor_alignment(product_version, "cursor", descriptor) == []
