"""Discover, deduplicate, queue and deliver project notifications."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.domain.run.autonomy_policy import is_unattended_preset
from governed_ai.core.workspace import Workspace
from governed_ai.notifications.config import SmtpSettings, load_smtp_settings, public_smtp_status
from governed_ai.notifications.smtp_transport import send_email

MAX_ATTEMPTS = 6


def _acquire_notification_lock(lock_path: Path, timeout_seconds: float = 2.0) -> str:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError):
            if time.monotonic() >= deadline:
                raise TimeoutError("notification dispatcher already active") from None
            time.sleep(0.05)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token)
        return token


def _release_notification_lock(lock_path: Path, token: str) -> None:
    try:
        if lock_path.read_text(encoding="utf-8") == token:
            lock_path.unlink(missing_ok=True)
    except OSError:
        pass


@dataclass(frozen=True, slots=True)
class NotificationCandidate:
    event_type: str
    source_ref: str
    source_version: str
    delivery: str
    recipient_group: str
    subject: str
    body: str

    @property
    def dedupe_key(self) -> str:
        material = f"{self.event_type}|{self.source_ref}|{self.source_version}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def notification_id(self) -> str:
        return f"NTF-{self.dedupe_key[:20].upper()}"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def _delivery(settings: SmtpSettings, event_type: str) -> str:
    value = settings.event_delivery.get(event_type, "off")
    if value != "profile":
        return value
    if is_unattended_preset(settings.autonomy_preset):
        return "digest"
    return "immediate"


def _candidate(
    settings: SmtpSettings,
    *,
    event_type: str,
    source_ref: str,
    source_version: Any,
    recipient_group: str,
    title: str,
    lines: list[str],
) -> NotificationCandidate | None:
    delivery = _delivery(settings, event_type)
    if delivery == "off":
        return None
    subject = f"[AgentTeam][{settings.project_id}] {title}"
    body = "\n".join(
        [
            f"Projet : {settings.project_name} ({settings.project_id})",
            f"Événement : {event_type}",
            f"Référence : {source_ref}",
            "",
            *lines,
            "",
            "Cette notification est informative. Les décisions restent soumises aux gates et autorisations du framework.",
        ]
    )
    return NotificationCandidate(
        event_type=event_type,
        source_ref=source_ref,
        source_version=str(source_version or "1"),
        delivery=delivery,
        recipient_group=recipient_group,
        subject=subject,
        body=body,
    )


def scan_notification_candidates(
    workspace: Workspace, settings: SmtpSettings
) -> list[NotificationCandidate]:
    ai_team = workspace.ai_team
    candidates: list[NotificationCandidate | None] = []

    for path in sorted((ai_team / "events").glob("*.yaml")):
        event = _load(path)
        if event.get("status") != "open":
            continue
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        checkpoint = details.get("human_checkpoint") if isinstance(details, dict) else None
        if isinstance(checkpoint, dict):
            candidates.append(
                _candidate(
                    settings,
                    event_type="ui_checkpoint",
                    source_ref=f"events/{path.name}",
                    source_version=checkpoint.get("observed_revision") or event.get("updated_at"),
                    recipient_group="action_required",
                    title=f"Interface prête à tester — {event.get('work_unit')}",
                    lines=[
                        f"Surface : {checkpoint.get('surface')}",
                        f"Accès : {checkpoint.get('command')}",
                        f"Révision observée : {checkpoint.get('observed_revision')}",
                        f"Scénarios : {checkpoint.get('acceptance_package_ref')}",
                        f"Pourquoi maintenant : {checkpoint.get('why')}",
                        "Le Run continue : ce checkpoint n'est pas une validation bloquante.",
                    ],
                )
            )
        if event.get("type") == "BLOCKER":
            candidates.append(
                _candidate(
                    settings,
                    event_type="global_stop",
                    source_ref=f"events/{path.name}",
                    source_version=event.get("created_at") or event.get("summary"),
                    recipient_group="critical",
                    title="Arrêt ou blocage critique",
                    lines=[
                        f"Résumé : {event.get('summary')}",
                        f"Work Unit : {event.get('work_unit')}",
                        "Une intervention humaine peut être requise immédiatement.",
                    ],
                )
            )
        elif event.get("type") == "RISK_ESCALATION":
            candidates.append(
                _candidate(
                    settings,
                    event_type="risk_escalation",
                    source_ref=f"events/{path.name}",
                    source_version=event.get("created_at") or event.get("summary"),
                    recipient_group="action_required",
                    title="Escalade de risque",
                    lines=[f"Résumé : {event.get('summary')}", f"Work Unit : {event.get('work_unit')}"],
                )
            )

    for path in sorted((ai_team / "decisions").glob("*.yaml")):
        decision = _load(path)
        if decision.get("status") != "pending_human":
            continue
        candidates.append(
            _candidate(
                settings,
                event_type="decision_required",
                source_ref=f"decisions/{path.name}",
                source_version=decision.get("revision"),
                recipient_group="action_required",
                title=f"Décision humaine requise — {decision.get('id')}",
                lines=[
                    f"Question : {decision.get('question')}",
                    f"Pourquoi : {decision.get('why_human_authority_is_required')}",
                    "Seul le sous-graphe dépendant doit rester en attente.",
                ],
            )
        )

    for path in sorted((ai_team / "runs" / "decisions").glob("*.yaml")):
        decision = _load(path)
        if decision.get("resolved") is not False:
            continue
        trigger = decision.get("trigger") if isinstance(decision.get("trigger"), dict) else {}
        candidates.append(
            _candidate(
                settings,
                event_type="decision_required",
                source_ref=f"runs/decisions/{path.name}",
                source_version=decision.get("created_at") or decision.get("id"),
                recipient_group="action_required",
                title=f"Décision de Run requise — {decision.get('id')}",
                lines=[
                    f"Run : {decision.get('run_id')}",
                    f"Work Unit : {decision.get('work_unit_id')}",
                    f"Déclencheur : {trigger.get('kind') or trigger.get('type') or 'enregistré'}",
                    "Le sous-graphe dépendant reste en attente de cette décision.",
                ],
            )
        )

    for path in sorted((ai_team / "runs" / "escalations").glob("*.yaml")):
        escalation = _load(path)
        candidates.append(
            _candidate(
                settings,
                event_type="risk_escalation",
                source_ref=f"runs/escalations/{path.name}",
                source_version=escalation.get("escalated_at") or escalation.get("id"),
                recipient_group="action_required",
                title=f"Plafond d'exécution resserré — {escalation.get('work_unit_id')}",
                lines=[
                    f"Dimension : {escalation.get('dimension')}",
                    f"État précédent : {escalation.get('previous_state')}",
                    f"Nouvel état : {escalation.get('new_state')}",
                    f"Raison : {escalation.get('reason')}",
                ],
            )
        )

    for path in sorted((ai_team / "release-candidates").glob("*.yaml")):
        candidate = _load(path)
        if candidate.get("status") != "ready_for_g3":
            continue
        candidates.append(
            _candidate(
                settings,
                event_type="release_candidate_ready",
                source_ref=f"release-candidates/{path.name}",
                source_version=candidate.get("revision"),
                recipient_group="action_required",
                title=f"Release candidate prête pour G3 — {candidate.get('id')}",
                lines=[
                    f"Environnement cible : {candidate.get('target_environment')}",
                    f"Work Units incluses : {', '.join(candidate.get('included_work_units') or [])}",
                    "La mise en production reste interdite sans décision G3.",
                ],
            )
        )

    for path in sorted((ai_team / "work-units").glob("*.yaml")):
        work_unit = _load(path)
        if work_unit.get("status") != "human_test":
            continue
        candidates.append(
            _candidate(
                settings,
                event_type="acceptance_ready",
                source_ref=f"work-units/{path.name}",
                source_version=work_unit.get("revision"),
                recipient_group="action_required",
                title=f"Incrément prêt pour vérification humaine — {work_unit.get('id')}",
                lines=[
                    f"Titre : {work_unit.get('title')}",
                    "Les vérifications agent sont terminées ; l'acceptation G4 reste une décision distincte.",
                ],
            )
        )

    for path in sorted((ai_team / "human-feedback").glob("*.yaml")):
        feedback = _load(path)
        status = feedback.get("status")
        if status not in {"reconciled", "needs_decision"}:
            continue
        group = "action_required" if status == "needs_decision" else "digest"
        candidates.append(
            _candidate(
                settings,
                event_type=(
                    "decision_required" if status == "needs_decision" else "human_feedback_reconciled"
                ),
                source_ref=f"human-feedback/{path.name}",
                source_version=feedback.get("revision"),
                recipient_group=group,
                title=f"Retour UI réconcilié — {feedback.get('id')}",
                lines=[
                    f"Work Unit : {feedback.get('work_unit')}",
                    f"Surface : {feedback.get('surface')}",
                    f"Résultat : {status}",
                    f"Justification : {(feedback.get('reconciliation') or {}).get('rationale')}",
                ],
            )
        )

    for path in sorted((ai_team / "runs").glob("*.yaml")):
        run = _load(path)
        status = run.get("status")
        if status not in {"completed", "stopped", "failed"}:
            continue
        is_failure = status in {"stopped", "failed"}
        event_type = "global_stop" if is_failure else "run_completed"
        report_path = ai_team / "runs" / "morning-reports" / f"{run.get('id')}.json"
        report = _load(report_path) if report_path.is_file() else {}
        candidates.append(
            _candidate(
                settings,
                event_type=event_type,
                source_ref=f"runs/{path.name}",
                source_version=run.get("revision"),
                recipient_group="critical" if is_failure else "digest",
                title=f"Run {status} — {run.get('id')}",
                lines=[
                    f"Statut : {status}",
                    f"Condition d'arrêt : {run.get('stop_condition')}",
                    f"Work Units terminées : {len(report.get('completed_work_units') or [])}",
                    f"Work Units en attente : {len(report.get('paused_work_units') or [])}",
                    f"Escalades : {len(report.get('risk_escalations') or [])}",
                ],
            )
        )

    return [candidate for candidate in candidates if candidate is not None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _enqueue(ai_team: Path, candidates: list[NotificationCandidate]) -> int:
    records_dir = ai_team / "notifications"
    records_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    now = _now().isoformat()
    for candidate in candidates:
        path = records_dir / f"{candidate.notification_id}.json"
        if path.exists():
            continue
        _write_record(
            path,
            {
                "id": candidate.notification_id,
                "dedupe_key": candidate.dedupe_key,
                "event_type": candidate.event_type,
                "source_ref": candidate.source_ref,
                "source_version": candidate.source_version,
                "delivery": candidate.delivery,
                "recipient_group": candidate.recipient_group,
                "subject": candidate.subject,
                "body": candidate.body,
                "status": "pending",
                "attempts": 0,
                "next_attempt_at": None,
                "last_error": None,
                "created_at": now,
                "updated_at": now,
                "sent_at": None,
            },
        )
        created += 1
    return created


def _pending_records(ai_team: Path) -> list[tuple[Path, dict[str, Any]]]:
    pending = []
    now = _now()
    for path in sorted((ai_team / "notifications").glob("NTF-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("status") not in {"pending", "failed"}:
            continue
        if int(record.get("attempts") or 0) >= MAX_ATTEMPTS:
            continue
        next_attempt = record.get("next_attempt_at")
        if next_attempt:
            try:
                if datetime.fromisoformat(next_attempt) > now:
                    continue
            except (TypeError, ValueError):
                pass
        pending.append((path, record))
    return pending


def _error_text(exc: Exception, settings: SmtpSettings) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if settings.password:
        message = message.replace(settings.password, "[REDACTED]")
    return message[:500]


def _mark_sent(items: list[tuple[Path, dict[str, Any]]]) -> None:
    now = _now().isoformat()
    for path, record in items:
        record.update(
            {"status": "sent", "sent_at": now, "updated_at": now, "last_error": None}
        )
        _write_record(path, record)


def _mark_failed(
    items: list[tuple[Path, dict[str, Any]]], exc: Exception, settings: SmtpSettings
) -> None:
    now = _now()
    for path, record in items:
        attempts = int(record.get("attempts") or 0) + 1
        delay = min(3600, 60 * (2 ** max(0, attempts - 1)))
        record.update(
            {
                "status": "failed",
                "attempts": attempts,
                "next_attempt_at": (now + timedelta(seconds=delay)).isoformat(),
                "last_error": _error_text(exc, settings),
                "updated_at": now.isoformat(),
            }
        )
        _write_record(path, record)


def _send_group(
    settings: SmtpSettings,
    items: list[tuple[Path, dict[str, Any]]],
    *,
    digest: bool,
) -> tuple[int, int]:
    if not items:
        return 0, 0
    recipient_group = str(items[0][1].get("recipient_group") or "digest")
    recipients = settings.recipients_for(recipient_group)
    if not recipients:
        return 0, 0
    if digest:
        subject = f"[AgentTeam][{settings.project_id}] Synthèse — {len(items)} notification(s)"
        sections = [
            f"Projet : {settings.project_name} ({settings.project_id})",
            "",
            *[
                f"--- {record.get('event_type')} / {record.get('source_ref')} ---\n{record.get('body')}"
                for _path, record in items
            ],
        ]
        body = "\n\n".join(sections)
    else:
        subject = str(items[0][1].get("subject"))
        body = str(items[0][1].get("body"))
    try:
        send_email(settings, recipients=recipients, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001 - SMTP failure must never block execution
        _mark_failed(items, exc, settings)
        return 0, len(items)
    _mark_sent(items)
    return len(items), 0


def dispatch_notifications(
    workspace: Workspace,
    *,
    include_digest: bool = False,
) -> dict[str, Any]:
    """Deliver configured notifications without propagating transport failures."""
    settings = load_smtp_settings(workspace.ai_team)
    result = {**public_smtp_status(settings), "queued": 0, "sent": 0, "failed": 0}
    if not settings.enabled or not settings.has_recipients:
        return result

    lock_path = workspace.ai_team / "locks" / "notifications.lock"
    lock_token = None
    try:
        lock_token = _acquire_notification_lock(lock_path)
        candidates = scan_notification_candidates(workspace, settings)
        result["queued"] = _enqueue(workspace.ai_team, candidates)
        if settings.username and not settings.password:
            return result

        pending = _pending_records(workspace.ai_team)
        immediate = [item for item in pending if item[1].get("delivery") == "immediate"]
        for item in immediate:
            sent, failed = _send_group(settings, [item], digest=False)
            result["sent"] += sent
            result["failed"] += failed

        if include_digest:
            digest_items = [item for item in pending if item[1].get("delivery") == "digest"]
            by_recipients: dict[tuple[str, ...], list[tuple[Path, dict[str, Any]]]] = {}
            for item in digest_items:
                recipients = settings.recipients_for(
                    str(item[1].get("recipient_group") or "digest")
                )
                if recipients:
                    by_recipients.setdefault(recipients, []).append(item)
            for items in by_recipients.values():
                sent, failed = _send_group(settings, items, digest=True)
                result["sent"] += sent
                result["failed"] += failed
    except Exception as exc:  # noqa: BLE001 - notifications are strictly non-blocking
        result["failed"] += 1
        result["error"] = _error_text(exc, settings)
    finally:
        if lock_token is not None:
            _release_notification_lock(lock_path, lock_token)
    return result


def send_test_notification(workspace: Workspace, recipient: str | None = None) -> dict[str, Any]:
    settings = load_smtp_settings(workspace.ai_team)
    result = public_smtp_status(settings)
    recipients = (recipient,) if recipient else settings.recipients_for("critical")
    if not settings.enabled or not recipients or (settings.username and not settings.password):
        return {**result, "sent": False}
    try:
        send_email(
            settings,
            recipients=recipients,
            subject=f"[AgentTeam][{settings.project_id}] Test SMTP",
            body=(
                f"Le transport SMTP du projet {settings.project_name} est opérationnel.\n"
                "Aucun secret n'est inclus dans ce message."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - report a test failure without exposing secrets
        return {**result, "sent": False, "error": _error_text(exc, settings)}
    return {**result, "sent": True}
