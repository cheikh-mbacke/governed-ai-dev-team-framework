"""Transmit consented Feedback Exports to the framework learning ingest."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import common
from governed_ai.feedback.commands.handlers import ExportParams, build_export_document


def _resolve_submit_url(meta: dict[str, Any]) -> str | None:
    env_url = (os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_URL") or "").strip()
    if env_url:
        return env_url
    configured = meta.get("telemetry_submit_url")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return None


def transmit_payload(payload: dict[str, Any], *, destination: str | None) -> dict[str, Any]:
    """POST the full export. No content redaction (ADR-009)."""
    transmission = {
        "status": "pending",
        "submitted_at": common.now_iso(),
        "destination": destination,
        "ack_id": None,
        "error": None,
    }
    if not destination:
        transmission["status"] = "local_outbox"
        return transmission

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        destination,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            ack_id = None
            try:
                parsed = json.loads(raw) if raw.strip() else {}
                if isinstance(parsed, dict):
                    ack_id = parsed.get("ack_id") or parsed.get("export_id")
            except json.JSONDecodeError:
                ack_id = None
            transmission["status"] = "transmitted"
            transmission["ack_id"] = ack_id or payload.get("export_id")
            return transmission
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        transmission["status"] = "failed"
        transmission["error"] = str(exc)
        return transmission


def build_and_submit(
    workspace: Workspace, *, output: str | None = None
) -> tuple[dict[str, Any], Any]:
    """Build a full consented export and attempt transmission."""
    meta = common.metadata(workspace)
    collection = meta.get("telemetry_collection") or "consented_share"
    if collection == "disabled":
        payload, path = build_export_document(
            workspace,
            ExportParams(detail_level="full", include_project_id=True, output=output),
        )
        payload["transmission"] = {
            "status": "skipped",
            "submitted_at": common.now_iso(),
            "destination": None,
            "ack_id": None,
            "error": "telemetry.collection is disabled",
        }
        common.validate_payload(workspace, payload, "feedback-export.schema.json")
        return payload, path

    payload, path = build_export_document(
        workspace,
        ExportParams(detail_level="full", include_project_id=True, output=output),
    )
    destination = _resolve_submit_url(meta)
    if not destination:
        outbox = workspace.ai_team / "metrics" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        path = outbox / f"{payload['export_id']}.json"
    payload["transmission"] = transmit_payload(payload, destination=destination)
    # Re-validate after transmission block is filled.
    common.validate_payload(workspace, payload, "feedback-export.schema.json")
    return payload, path
