"""Shared helpers for structured framework-learning feedback."""

from __future__ import annotations

import json
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from governed_ai.core.persistence.io import load_json
from governed_ai.core.persistence.io import load_yaml as _load_yaml
from governed_ai.core.workspace import Workspace


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def generated_id(prefix: str) -> str:
    stamp = now_utc().strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


def load_yaml(path: Path) -> dict:
    data = _load_yaml(path)
    return data if isinstance(data, dict) else {}


def load_yaml_directory(path: Path) -> list[tuple[Path, dict]]:
    if not path.exists():
        return []
    loaded = []
    for item in sorted(path.glob("*.yaml")):
        loaded.append((item, load_yaml(item)))
    return loaded


def metadata(workspace: Workspace) -> dict:
    ai = workspace.ai_team
    profile = load_yaml(ai / "project-profile.yaml")
    state = load_yaml(ai / "state" / "project-state.yaml")
    framework = load_json(ai / "framework-version.json")
    constitution = load_yaml(ai / "constitution" / "constitution.yaml")
    return {
        "project_id": profile.get("project", {}).get("id") or state.get("project_id"),
        "framework_version": framework.get("version"),
        "constitution_version": (
            state.get("constitution_version")
            or constitution.get("constitution", {}).get("version")
        ),
        "phase": state.get("phase"),
    }


def validate_payload(workspace: Workspace, payload: dict, schema_name: str) -> None:
    schema = load_json(workspace.ai_team / "schemas" / schema_name)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        messages = []
        for error in errors:
            location = "/".join(map(str, error.path)) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValueError("Invalid feedback payload: " + "; ".join(messages))


def atomic_write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    _atomic_write_text(path, content)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def find_work_unit(workspace: Workspace, work_unit_id: str) -> tuple[Path, dict] | None:
    directory = workspace.ai_team / "work-units"
    exact = directory / f"{work_unit_id}.yaml"
    if exact.exists():
        return exact, load_yaml(exact)
    matches = sorted(directory.glob(f"{work_unit_id}-*.yaml"))
    if len(matches) == 1:
        return matches[0], load_yaml(matches[0])
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ValueError(f"Work Unit id {work_unit_id!r} is ambiguous: {names}")
    for path, data in load_yaml_directory(directory):
        if data.get("id") == work_unit_id:
            return path, data
    return None


def relates_to_work_unit(payload: dict, work_unit_id: str | None) -> bool:
    if work_unit_id is None:
        return True
    if payload.get("work_unit") == work_unit_id:
        return True
    if work_unit_id in (payload.get("work_units") or []):
        return True
    impact = payload.get("impact") or {}
    return work_unit_id in (impact.get("affected_work_units") or [])


def observation_summary(observations: list[dict]) -> tuple[dict, dict]:
    unresolved = {"open", "acknowledged", "candidate_change"}
    summary = {
        "total": len(observations),
        "open": sum(item.get("status") in unresolved for item in observations),
        "by_category": dict(sorted(Counter(item.get("category") for item in observations).items())),
        "by_origin": dict(
            sorted(
                Counter(
                    (item.get("classification") or {}).get("origin")
                    for item in observations
                ).items()
            )
        ),
        "by_severity": dict(sorted(Counter(item.get("severity") for item in observations).items())),
    }
    signals = {
        "blocked_minutes": sum(
            int((item.get("impact") or {}).get("blocked_minutes") or 0)
            for item in observations
        ),
        "rework_observations": sum(
            bool((item.get("impact") or {}).get("rework_required"))
            for item in observations
        ),
        "human_interventions": sum(
            bool((item.get("impact") or {}).get("human_intervention"))
            for item in observations
        ),
    }
    return summary, signals
