"""Schema validation helpers for governance commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.io import load_json


def validate_against_schema(
    workspace_ai_team: Path,
    payload: dict[str, Any],
    schema_name: str,
    *,
    root_path: str = "/payload",
) -> None:
    schema = load_json(workspace_ai_team / "schemas" / schema_name)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if not errors:
        return
    first = errors[0]
    pointer = root_path
    if first.path:
        pointer += "/" + "/".join(str(part) for part in first.path)
    raise GatewayError(ErrorCode.INVALID_SCHEMA, first.message, pointer)
