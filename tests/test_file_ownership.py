"""Tests for file ownership inventory and golden object fixtures."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = ROOT / "tests" / "fixtures" / "legacy-0.4"
OBJECTS_DIR = FIXTURES_ROOT / "objects"
INVENTORY_PATH = FIXTURES_ROOT / "file-ownership-inventory.json"
OBJECTS_MANIFEST_PATH = FIXTURES_ROOT / "objects-manifest.json"
SCHEMAS_DIR = ROOT / ".ai-team" / "schemas"

sys.path.insert(0, str(ROOT / "scripts" / "ai-team"))
from validate_ownership import (  # noqa: E402
    VALID_OWNERS,
    classify_owner,
    iter_scope_files,
    validate_ownership,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_schema_valid(instance, schema_name: str) -> None:
    schema = load_json(SCHEMAS_DIR / schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(f"  - {e.message}" for e in errors)
        raise AssertionError(f"{schema_name} validation failed:\n{messages}")


class FileOwnershipInventoryTests(unittest.TestCase):
    def test_inventory_covers_all_scope_files(self):
        errors = validate_ownership(ROOT, INVENTORY_PATH)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_classify_owner_matches_inventory(self):
        inventory = load_json(INVENTORY_PATH)
        for path, owner in inventory["files"].items():
            self.assertEqual(classify_owner(path), owner, path)

    def test_inventory_owner_values_are_valid_enum(self):
        inventory = load_json(INVENTORY_PATH)
        for path, owner in inventory["files"].items():
            self.assertIn(owner, VALID_OWNERS, f"{path} has invalid owner {owner!r}")

    def test_scope_file_count_matches_inventory(self):
        scope_count = len(iter_scope_files(ROOT))
        inventory_count = len(load_json(INVENTORY_PATH)["files"])
        self.assertEqual(scope_count, inventory_count)

    def test_validate_ownership_script_importable(self):
        self.assertTrue(INVENTORY_PATH.is_file())


class GoldenObjectFixturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(OBJECTS_MANIFEST_PATH)

    def test_manifest_lists_all_object_types(self):
        object_types = {entry["object_type"] for entry in self.manifest["objects"]}
        expected = {
            "project-profile",
            "project-state",
            "work-unit",
            "gate-decision",
            "observation",
            "retrospective",
            "installation-manifest",
        }
        self.assertEqual(object_types, expected)

    def test_fixture_hashes_match_manifest(self):
        for entry in self.manifest["objects"]:
            rel_path = entry["path"]
            fixture_path = FIXTURES_ROOT / rel_path
            self.assertTrue(fixture_path.is_file(), rel_path)
            self.assertEqual(
                sha256_file(fixture_path),
                entry["sha256"],
                f"Hash mismatch for {rel_path} — regenerate objects-manifest.json",
            )

    def test_project_profile_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "project-profile.yaml")
        assert_schema_valid(data, "project-profile.schema.json")

    def test_project_state_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "project-state.yaml")
        assert_schema_valid(data, "project-state.schema.json")

    def test_work_unit_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "work-unit.yaml")
        assert_schema_valid(data, "work-unit.schema.json")

    def test_gate_decision_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "gate-decision.yaml")
        assert_schema_valid(data, "gate-decision.schema.json")

    def test_observation_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "observation.yaml")
        assert_schema_valid(data, "observation.schema.json")

    def test_retrospective_validates_against_schema(self):
        data = load_yaml(OBJECTS_DIR / "retrospective.yaml")
        assert_schema_valid(data, "retrospective.schema.json")

    def test_installation_manifest_has_required_fields(self):
        data = load_json(OBJECTS_DIR / "installation-manifest.json")
        self.assertEqual(data["schema_version"], 1)
        self.assertIsInstance(data["version"], str)
        self.assertIsInstance(data["managed_files"], list)
        self.assertGreater(len(data["managed_files"]), 0)


if __name__ == "__main__":
    unittest.main()
