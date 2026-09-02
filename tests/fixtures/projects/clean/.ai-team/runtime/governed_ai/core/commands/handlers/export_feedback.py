"""ExportFeedback command handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback.commands.handlers import ExportParams, build_export_document

SENSITIVE_DETAIL_LEVELS = frozenset({"full"})


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


def handle_export_feedback(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    ensure_feedback_allowed(workspace_root)

    detail_level = payload.get("detail_level", "structured")
    if detail_level not in {"aggregate", "structured", "full"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.detail_level must be aggregate, structured, or full",
            "/payload/detail_level",
        )

    if detail_level in SENSITIVE_DETAIL_LEVELS:
        consume_human_authorization(
            envelope,
            workspace_ai_team=workspace_root.ai_team,
            transaction=transaction,
        )

    params = ExportParams(
        detail_level=detail_level,
        include_project_id=bool(payload.get("include_project_id")),
        output=_resolve_output_path(workspace_root, payload.get("output")),
    )
    try:
        document, path = build_export_document(workspace_root, params)
    except ValueError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/payload") from exc

    if path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"export output {path.name!r} already exists",
            "/payload/output",
        )

    transaction.plan_json_write(path, document)
    relative = path.relative_to(workspace_root.root).as_posix()
    return {
        "affected": [
            {
                "kind": "feedback_export",
                "detail_level": detail_level,
                "path": relative,
                "observation_count": document["summary"].get("total", 0),
                "retrospective_count": document["summary"].get("retrospectives", 0),
            }
        ],
    }, []
