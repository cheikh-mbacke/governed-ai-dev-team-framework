"""GenerateRetrospective command handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback.commands.handlers import (
    RetrospectiveParams,
    build_retrospective_document,
)


def _resolve_output_path(workspace_root, raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    resolved = Path(raw_path).expanduser().resolve()
    try:
        resolved.relative_to(workspace_root.root)
    except ValueError as exc:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "output path must stay inside the workspace",
            "/payload/output",
        ) from exc
    return str(resolved)


def handle_generate_retrospective(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    ensure_feedback_allowed(workspace_root)

    scope = payload.get("scope")
    if scope not in {"work_unit", "project"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.scope must be work_unit or project",
            "/payload/scope",
        )

    work_unit_id = payload.get("work_unit_id")
    if scope == "work_unit" and not work_unit_id:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.work_unit_id is required for work_unit scope",
            "/payload/work_unit_id",
        )
    if scope == "project":
        work_unit_id = None

    params = RetrospectiveParams(
        work_unit=work_unit_id,
        project=scope == "project",
        notes=payload.get("notes"),
        output=_resolve_output_path(workspace_root, payload.get("output")),
    )
    try:
        document, path = build_retrospective_document(workspace_root, params)
    except ValueError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/payload") from exc

    if path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"retrospective output {path.name!r} already exists",
            "/payload/output",
        )

    transaction.plan_yaml_write(path, document)
    relative = path.relative_to(workspace_root.root).as_posix()
    return {
        "affected": [
            {
                "kind": "retrospective",
                "id": document["id"],
                "scope": document["scope"]["type"],
                "path": relative,
            }
        ],
    }, []
