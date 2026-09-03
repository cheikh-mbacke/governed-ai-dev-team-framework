"""Transmit consented Feedback Exports to the framework learning ingest."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import common
from governed_ai.feedback.commands.handlers import ExportParams, build_export_document

RETRYABLE_TRANSMISSION_STATUSES = frozenset({"pending", "local_outbox", "failed"})
CURRENT_TERMS_VERSION = "1.0"
_DEFAULT_BACKOFF_SECONDS = (0.5, 1.0, 2.0)


def _submit_attempts() -> int:
    raw = (os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_ATTEMPTS") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return 3


def outbox_directory(workspace: Workspace) -> Path:
    return workspace.ai_team / "metrics" / "outbox"


def transmitted_directory(workspace: Workspace) -> Path:
    return outbox_directory(workspace) / "transmitted"


def _resolve_submit_url(meta: dict[str, Any]) -> str | None:
    env_url = (os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_URL") or "").strip()
    if env_url:
        return env_url
    configured = meta.get("telemetry_submit_url")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return None


def _resolve_submit_token() -> str | None:
    token = (os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_TOKEN") or "").strip()
    return token or None


def _payload_for_wire(payload: dict[str, Any]) -> dict[str, Any]:
    """POST body without a stale transmission block (receiver re-validates schema)."""
    wire = dict(payload)
    wire.pop("transmission", None)
    return wire


def ensure_terms_accepted(meta: dict[str, Any]) -> None:
    """Require install-time terms acceptance under consented_share (ADR-009)."""
    collection = meta.get("telemetry_collection") or "consented_share"
    if collection == "disabled":
        return
    accepted_at = meta.get("telemetry_terms_accepted_at")
    if not (isinstance(accepted_at, str) and accepted_at.strip()):
        raise ValueError(
            "telemetry.terms_accepted_at is required under consented_share "
            "(re-install or set the field after accepting current terms)"
        )
    terms_version = meta.get("telemetry_terms_version") or CURRENT_TERMS_VERSION
    if str(terms_version) != CURRENT_TERMS_VERSION:
        raise ValueError(
            f"telemetry.terms_version {terms_version!r} does not match "
            f"current {CURRENT_TERMS_VERSION!r}"
        )


def transmit_payload(
    payload: dict[str, Any],
    *,
    destination: str | None,
    attempts: int | None = None,
) -> dict[str, Any]:
    """POST the full export with bounded retries. No content redaction (ADR-009)."""
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
    headers = {"Content-Type": "application/json; charset=utf-8"}
    token = _resolve_submit_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_error: str | None = None
    max_attempts = max(1, attempts if attempts is not None else _submit_attempts())
    for attempt in range(max_attempts):
        request = urllib.request.Request(
            destination,
            data=body,
            headers=headers,
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
                transmission["error"] = None
                return transmission
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            if attempt + 1 < max_attempts:
                delay = _DEFAULT_BACKOFF_SECONDS[
                    min(attempt, len(_DEFAULT_BACKOFF_SECONDS) - 1)
                ]
                time.sleep(delay)

    transmission["status"] = "failed"
    transmission["error"] = last_error
    return transmission


def _outbox_path(workspace: Workspace, export_id: str) -> Path:
    directory = outbox_directory(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{export_id}.json"


def _archive_transmitted(workspace: Workspace, path: Path, document: dict[str, Any]) -> Path:
    """Move a successfully transmitted outbox item into outbox/transmitted/."""
    archive_dir = transmitted_directory(workspace)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / path.name
    common.atomic_write_json(target, document)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return target


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
        new_status = document["transmission"]["status"]
        if new_status == "transmitted":
            archived = _archive_transmitted(workspace, path, document)
            results.append(
                FlushItemResult(
                    export_id=export_id,
                    path=archived,
                    status=new_status,
                    error=None,
                )
            )
        else:
            common.atomic_write_json(path, document)
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
    if collection != "disabled":
        ensure_terms_accepted(meta)
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
