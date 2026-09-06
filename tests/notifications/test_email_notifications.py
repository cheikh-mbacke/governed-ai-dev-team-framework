"""SMTP notification routing, delivery and failure-isolation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from governed_ai.core.workspace import Workspace
from governed_ai.notifications.config import (
    DEFAULT_SMTP_FROM,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_SECURITY,
    DEFAULT_SMTP_USERNAME,
    load_smtp_settings,
)
from governed_ai.notifications.service import dispatch_notifications
from governed_ai.notifications.smtp_transport import send_email


def _workspace(tmp_path: Path, *, preset: str) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    for directory in (
        "decisions",
        "events",
        "human-feedback",
        "locks",
        "notifications",
        "release-candidates",
        "runs/morning-reports",
        "work-units",
    ):
        (ai_team / directory).mkdir(parents=True, exist_ok=True)
    profile = {
        "project": {"id": "mail-test", "name": "Mail Test"},
        "autonomy": {"preset": preset, "level": 3},
        "notifications": {
            "email": {
                "enabled": True,
                "from": DEFAULT_SMTP_FROM,
                "transport": {
                    "host": DEFAULT_SMTP_HOST,
                    "port": DEFAULT_SMTP_PORT,
                    "security": DEFAULT_SMTP_SECURITY,
                    "username": DEFAULT_SMTP_USERNAME,
                    "password_env": "GOVERNED_AI_SMTP_PASSWORD",
                    "connect_timeout_seconds": 3,
                },
                "recipients": {
                    "critical": ["critical@example.test"],
                    "action_required": ["product@example.test"],
                    "digest": ["digest@example.test"],
                },
                "events": {
                    "global_stop": "immediate",
                    "decision_required": "immediate",
                    "risk_escalation": "immediate",
                    "release_candidate_ready": "immediate",
                    "acceptance_ready": "profile",
                    "ui_checkpoint": "profile",
                    "human_feedback_reconciled": "digest",
                    "run_completed": "digest",
                },
            }
        },
    }
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False), encoding="utf-8"
    )
    return Workspace.from_root(tmp_path)


def _checkpoint(workspace: Workspace) -> None:
    event = {
        "id": "EVT-UI-READY",
        "type": "HANDOFF",
        "work_unit": "WU-UI-001",
        "summary": "UI ready",
        "status": "open",
        "details": {
            "human_checkpoint": {
                "surface": "dashboard",
                "command": "http://localhost:3000/dashboard",
                "observed_revision": "a" * 40,
                "acceptance_package_ref": ".ai-team/acceptance/UAT-UI.yaml",
                "why": "First coherent slice",
                "non_blocking": True,
            }
        },
    }
    (workspace.ai_team / "events" / "EVT-UI-READY.yaml").write_text(
        yaml.safe_dump(event, sort_keys=False), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def smtp_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOVERNED_AI_SMTP_PASSWORD", "test-only-secret")


def test_seed_uses_requested_public_smtp_defaults() -> None:
    profile = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2]
            / "distribution"
            / "payload"
            / "seeds"
            / "project-profile.yaml"
        ).read_text(encoding="utf-8")
    )
    transport = profile["notifications"]["email"]["transport"]
    assert transport == {
        "host": "mail.agenteam.fr",
        "port": 465,
        "security": "ssl",
        "username": "support@agenteam.fr",
        "password_env": "GOVERNED_AI_SMTP_PASSWORD",
        "connect_timeout_seconds": 10,
    }
    assert "password" not in transport


def test_transport_uses_implicit_ssl_and_complete_username(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path, preset="supervised_copilots")
    settings = load_smtp_settings(workspace.ai_team)
    calls = {}

    class FakeSmtpSsl:
        def __init__(self, host, port, *, timeout, context):
            calls["connect"] = (host, port, timeout, context is not None)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, username, password):
            calls["login"] = (username, password)

        def send_message(self, message):
            calls["message"] = message

    monkeypatch.setattr(
        "governed_ai.notifications.smtp_transport.smtplib.SMTP_SSL", FakeSmtpSsl
    )
    send_email(
        settings,
        recipients=("recipient@example.test",),
        subject="Test",
        body="Test body",
    )

    assert calls["connect"][:3] == ("mail.agenteam.fr", 465, 3.0)
    assert calls["login"] == ("support@agenteam.fr", "test-only-secret")
    assert calls["message"]["From"] == "support@agenteam.fr"


def test_supervised_ui_checkpoint_is_sent_immediately_and_deduplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path, preset="supervised_copilots")
    _checkpoint(workspace)
    sent = []

    def fake_send(_settings, *, recipients, subject, body):
        sent.append((recipients, subject, body))

    monkeypatch.setattr("governed_ai.notifications.service.send_email", fake_send)
    first = dispatch_notifications(workspace)
    second = dispatch_notifications(workspace)

    assert first["queued"] == 1
    assert first["sent"] == 1
    assert second["queued"] == 0
    assert second["sent"] == 0
    assert len(sent) == 1
    assert sent[0][0] == ("product@example.test",)
    assert "Run continue" in sent[0][2]
    record_path = next((workspace.ai_team / "notifications").glob("NTF-*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "sent"
    assert record["attempts"] == 0
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "distribution"
            / "payload"
            / ".ai-team"
            / "schemas"
            / "notification.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(record)


def test_unattended_ui_checkpoint_waits_for_grouped_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path, preset="unattended_maximal")
    _checkpoint(workspace)
    sent = []
    monkeypatch.setattr(
        "governed_ai.notifications.service.send_email",
        lambda _settings, **message: sent.append(message),
    )

    immediate = dispatch_notifications(workspace)
    assert immediate["queued"] == 1
    assert immediate["sent"] == 0
    assert sent == []

    digest = dispatch_notifications(workspace, include_digest=True)
    assert digest["sent"] == 1
    assert len(sent) == 1
    assert "Synthèse" in sent[0]["subject"]


def test_smtp_failure_is_persisted_and_never_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path, preset="supervised_copilots")
    (workspace.ai_team / "events" / "EVT-STOP.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "EVT-STOP",
                "type": "BLOCKER",
                "work_unit": None,
                "summary": "Unsafe state",
                "status": "open",
                "details": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    def fail_send(*_args, **_kwargs):
        raise OSError("SMTP unavailable; credential=test-only-secret")

    monkeypatch.setattr("governed_ai.notifications.service.send_email", fail_send)
    result = dispatch_notifications(workspace)

    assert result["failed"] == 1
    record_path = next((workspace.ai_team / "notifications").glob("NTF-*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["attempts"] == 1
    assert record["next_attempt_at"]
    assert "test-only-secret" not in record["last_error"]
    assert "[REDACTED]" in record["last_error"]


def test_missing_password_keeps_delivery_pending_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOVERNED_AI_SMTP_PASSWORD")
    workspace = _workspace(tmp_path, preset="supervised_copilots")
    _checkpoint(workspace)
    monkeypatch.setattr(
        "governed_ai.notifications.service.send_email",
        lambda *_args, **_kwargs: pytest.fail("network transport should not be called"),
    )

    result = dispatch_notifications(workspace)
    settings = load_smtp_settings(workspace.ai_team)

    assert result["queued"] == 1
    assert result["sent"] == 0
    assert settings.ready is False
    assert "password=" not in repr(settings)
