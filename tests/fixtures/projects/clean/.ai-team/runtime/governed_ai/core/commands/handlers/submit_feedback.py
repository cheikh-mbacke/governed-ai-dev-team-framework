"""SubmitFeedback command handler — consented full remount (ADR-009)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback.submit import build_and_submit


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


def handle_submit_feedback(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    ensure_feedback_allowed(workspace_root)

    try:
        document, path = build_and_submit(
            workspace_root,
            output=_resolve_output_path(workspace_root, payload.get("output")),
        )
    except ValueError as exc:
        raise GatewayError(ErrorCode.UNSUPPORTED_CONTRACT, str(exc), "/payload") from exc

    if path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"export output {path.name!r} already exists",
            "/payload/output",
        )

    transaction.plan_json_write(path, document)
    relative = path.relative_to(workspace_root.root).as_posix()
    transmission = document.get("transmission") or {}
    return {
        "affected": [
            {
                "kind": "feedback_export",
                "detail_level": document["detail_level"],
                "path": relative,
                "observation_count": document["summary"].get("total", 0),
                "retrospective_count": document["summary"].get("retrospectives", 0),
                "transmission_status": transmission.get("status"),
                "submitted": True,
            }
        ],
    }, []
