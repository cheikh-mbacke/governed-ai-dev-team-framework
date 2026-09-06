"""Product defaults for Feedback Export transmission (ADR-009)."""

from __future__ import annotations

from pathlib import Path

# Production ingestion tunnel (Governed AI Feedback Ingestion).
DEFAULT_FEEDBACK_SUBMIT_URL = "https://feedback.agenteam.fr/v1/feedback-exports"
DEFAULT_ENROLL_URL = "https://feedback.agenteam.fr/v1/installations/enroll"

# Public product enrollment Bearer — must match tunnel GAI_ENROLLMENT_TOKEN.
# Not an ingest secret; each install still receives a unique HMAC key.
DEFAULT_ENROLLMENT_TOKEN = "gai-enroll-public-v1-agenteam"

FEEDBACK_INGEST_SECRETS_REL = Path(".ai-team") / "secrets" / "feedback-ingest.json"
