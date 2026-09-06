"""SMTP notification configuration with secret-safe defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SMTP_HOST = "mail.agenteam.fr"
DEFAULT_SMTP_PORT = 465
DEFAULT_SMTP_SECURITY = "ssl"
DEFAULT_SMTP_USERNAME = "support@agenteam.fr"
DEFAULT_SMTP_FROM = "support@agenteam.fr"
DEFAULT_PASSWORD_ENV = "GOVERNED_AI_SMTP_PASSWORD"
SMTP_SECRET_REL = Path("secrets") / "smtp.json"

DEFAULT_EVENT_DELIVERY = {
    "global_stop": "immediate",
    "decision_required": "immediate",
    "risk_escalation": "immediate",
    "release_candidate_ready": "immediate",
    "acceptance_ready": "profile",
    "ui_checkpoint": "profile",
    "human_feedback_reconciled": "digest",
    "run_completed": "digest",
}


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    enabled: bool
    host: str
    port: int
    security: str
    username: str
    sender: str
    password_env: str
    password: str = field(repr=False)
    connect_timeout_seconds: float = 10.0
    recipients: dict[str, tuple[str, ...]] = field(default_factory=dict)
    event_delivery: dict[str, str] = field(default_factory=dict)
    autonomy_preset: str = "supervised_copilots"
    project_id: str = "unknown-project"
    project_name: str = "Unknown project"

    def recipients_for(self, group: str) -> tuple[str, ...]:
        direct = self.recipients.get(group) or ()
        if direct:
            return direct
        if group == "critical":
            return self.recipients.get("action_required") or self.recipients.get("digest") or ()
        if group == "action_required":
            return self.recipients.get("digest") or ()
        return ()

    @property
    def has_recipients(self) -> bool:
        return any(self.recipients.values())

    @property
    def ready(self) -> bool:
        credentials_ready = not self.username or bool(self.password)
        return self.enabled and self.has_recipients and credentials_ready


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _load_local_password(ai_team: Path) -> str:
    path = ai_team / SMTP_SECRET_REL
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    password = payload.get("password") if isinstance(payload, dict) else None
    return str(password) if password else ""


def load_smtp_settings(ai_team: Path) -> SmtpSettings:
    profile_path = ai_team / "project-profile.yaml"
    try:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        profile = {}
    email_config = _mapping(_mapping(profile.get("notifications")).get("email"))
    transport = _mapping(email_config.get("transport"))
    recipients = _mapping(email_config.get("recipients"))
    events = dict(DEFAULT_EVENT_DELIVERY)
    events.update(
        {
            str(key): str(value)
            for key, value in _mapping(email_config.get("events")).items()
            if value in {"immediate", "digest", "off", "profile"}
        }
    )
    password_env = str(transport.get("password_env") or DEFAULT_PASSWORD_ENV)
    password = os.environ.get(password_env) or _load_local_password(ai_team)
    project = _mapping(profile.get("project"))
    autonomy = _mapping(profile.get("autonomy"))
    port_value = os.environ.get("GOVERNED_AI_SMTP_PORT") or transport.get("port")
    try:
        port = int(port_value or DEFAULT_SMTP_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_SMTP_PORT
    try:
        timeout = float(transport.get("connect_timeout_seconds", 10.0))
    except (TypeError, ValueError):
        timeout = 10.0
    return SmtpSettings(
        enabled=bool(email_config.get("enabled", False)),
        host=str(
            os.environ.get("GOVERNED_AI_SMTP_HOST")
            or transport.get("host")
            or DEFAULT_SMTP_HOST
        ),
        port=port,
        security=str(
            os.environ.get("GOVERNED_AI_SMTP_SECURITY")
            or transport.get("security")
            or DEFAULT_SMTP_SECURITY
        ),
        username=str(
            os.environ.get("GOVERNED_AI_SMTP_USERNAME")
            or transport.get("username")
            or DEFAULT_SMTP_USERNAME
        ),
        sender=str(
            os.environ.get("GOVERNED_AI_SMTP_FROM")
            or email_config.get("from")
            or DEFAULT_SMTP_FROM
        ),
        password_env=password_env,
        password=password,
        connect_timeout_seconds=max(1.0, timeout),
        recipients={
            "critical": _strings(recipients.get("critical")),
            "action_required": _strings(recipients.get("action_required")),
            "digest": _strings(recipients.get("digest")),
        },
        event_delivery=events,
        autonomy_preset=str(autonomy.get("preset") or "supervised_copilots"),
        project_id=str(project.get("id") or "unknown-project"),
        project_name=str(project.get("name") or project.get("id") or "Unknown project"),
    )


def public_smtp_status(settings: SmtpSettings) -> dict[str, Any]:
    missing: list[str] = []
    if settings.enabled and not settings.has_recipients:
        missing.append("recipients")
    if settings.enabled and settings.username and not settings.password:
        missing.append(settings.password_env)
    return {
        "enabled": settings.enabled,
        "ready": settings.ready,
        "host": settings.host,
        "port": settings.port,
        "security": settings.security,
        "username": settings.username,
        "sender": settings.sender,
        "missing": missing,
    }
