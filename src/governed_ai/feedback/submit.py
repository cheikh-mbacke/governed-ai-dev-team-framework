"""Transmit consented Feedback Exports to the framework learning ingest."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import common
from governed_ai.feedback.commands.handlers import ExportParams, build_export_document

RETRYABLE_TRANSMISSION_STATUSES = frozenset({"pending", "local_outbox", "failed"})


def outbox_directory(workspace: Workspace) -> Path:
    return workspace.ai_team / "metrics" / "outbox"


def _resolve_submit_url(meta: dict[str, Any]) -> str | None:
    env_url = (os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_URL") or "").strip()
    if env_url:
        return env_url
    configured = meta.get("telemetry_submit_url")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return None


def _payload_for_wire(payload: dict[str, Any]) -> dict[str, Any]:
    """POST body without a stale transmission block (receiver re-validates schema)."""
    wire = dict(payload)
    wire.pop("transmission", None)
    return wire


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

    body = json.dumps(_payload_for_wire(payload), ensure_ascii=False).encode("utf-8")
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


def _outbox_path(workspace: Workspace, export_id: str) -> Path:
    directory = outbox_directory(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{export_id}.json"


@dataclass(frozen=True, slots=True)
class FlushItemResult:
    export_id: str
    path: Path
    status: str
    error: str | None = None


def flush_outbox(workspace: Workspace) -> list[FlushItemResult]:
    """Retry pending/failed/local_outbox exports when a submit URL is available."""
    meta = common.metadata(workspace)
    collection = meta.get("telemetry_collection") or "consented_share"
    directory = outbox_directory(workspace)
    if not directory.is_dir():
        return []

    results: list[FlushItemResult] = []
    destination = None if collection == "disabled" else _resolve_submit_url(meta)

    for path in sorted(directory.glob("EXP-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            results.append(
                FlushItemResult(
                    export_id=path.stem,
                    path=path,
                    status="failed",
                    error=f"unreadable outbox file: {exc}",
                )
            )
            continue
        if not isinstance(document, dict):
            results.append(
                FlushItemResult(
                    export_id=path.stem,
                    path=path,
                    status="failed",
                    error="outbox payload must be a JSON object",
                )
            )
            continue

        export_id = str(document.get("export_id") or path.stem)
        transmission = document.get("transmission") or {}
        status = transmission.get("status")
        if status not in RETRYABLE_TRANSMISSION_STATUSES:
            continue

        if collection == "disabled":
            document["transmission"] = {
                "status": "skipped",
                "submitted_at": common.now_iso(),
                "destination": None,
                "ack_id": None,
                "error": "telemetry.collection is disabled",
            }
            common.atomic_write_json(path, document)
            results.append(
                FlushItemResult(export_id=export_id, path=path, status="skipped")
            )
            continue

        if not destination:
            # Keep retryable; surface as local_outbox when still offline.
            if status != "local_outbox":
                document["transmission"] = {
                    "status": "local_outbox",
                    "submitted_at": common.now_iso(),
                    "destination": None,
                    "ack_id": None,
                    "error": None,
                }
                common.atomic_write_json(path, document)
            results.append(
                FlushItemResult(export_id=export_id, path=path, status="local_outbox")
            )
            continue

        document["transmission"] = transmit_payload(document, destination=destination)
        common.validate_payload(workspace, document, "feedback-export.schema.json")
        common.atomic_write_json(path, document)
        new_status = document["transmission"]["status"]
        results.append(
            FlushItemResult(
                export_id=export_id,
                path=path,
                status=new_status,
                error=document["transmission"].get("error"),
            )
        )
    return results


def build_and_submit(
    workspace: Workspace, *, output: str | None = None
) -> tuple[dict[str, Any], Any]:
    """Build a full consented export and attempt transmission.

    Always drains the local outbox first when a destination URL is configured
    (or marks items skipped when collection is disabled). Failed or offline
    exports land under `.ai-team/metrics/outbox/` for later flush/retry.
    """
    meta = common.metadata(workspace)
    collection = meta.get("telemetry_collection") or "consented_share"
    flush_outbox(workspace)

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
    payload["transmission"] = transmit_payload(payload, destination=destination)
    status = payload["transmission"]["status"]
    if output is None and status in RETRYABLE_TRANSMISSION_STATUSES:
        path = _outbox_path(workspace, str(payload["export_id"]))
    # Re-validate after transmission block is filled.
    common.validate_payload(workspace, payload, "feedback-export.schema.json")
    return payload, path
