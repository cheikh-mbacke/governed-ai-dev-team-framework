#!/usr/bin/env python3
"""HTTP receiver for consented Feedback Exports (framework learning side).

Bind behind a tunnel later; this process only accepts POST /ingest JSON bodies
matching feedback-export.schema.json, writes learning/inbox, and refreshes the
aggregate index.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from governed_ai.learning.aggregate import write_aggregate

# Reuse ingest validation/write path.
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "ai-team"))
from ingest_feedback import ingest_document  # noqa: E402

INBOX = _REPO_ROOT / "learning" / "inbox"


class FeedbackHandler(BaseHTTPRequestHandler):
    server_version = "GovernedAIFeedbackReceiver/1.0"
    expected_token: str | None = None

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _unauthorized(self) -> bool:
        if not self.expected_token:
            return False
        header = self.headers.get("Authorization") or ""
        expected = f"Bearer {self.expected_token}"
        if header.strip() != expected:
            self._send_json(401, {"error": "unauthorized"})
            return True
        return False

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/ingest", "/"}:
            self._send_json(404, {"error": "not found"})
            return
        if self._unauthorized():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 32 * 1024 * 1024:
            self._send_json(400, {"error": "invalid content length"})
            return
        try:
            document = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "body must be JSON"})
            return
        if not isinstance(document, dict):
            self._send_json(400, {"error": "payload must be a JSON object"})
            return
        try:
            target = ingest_document(document, inbox=INBOX)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        write_aggregate(inbox=INBOX)
        export_id = document.get("export_id") or target.stem
        self._send_json(200, {"ack_id": f"ACK-{export_id}", "export_id": export_id})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--token",
        default="",
        help="Optional Bearer token (or set GOVERNED_AI_FEEDBACK_SUBMIT_TOKEN)",
    )
    args = parser.parse_args()
    import os

    token = (args.token or os.environ.get("GOVERNED_AI_FEEDBACK_SUBMIT_TOKEN") or "").strip()
    FeedbackHandler.expected_token = token or None
    server = ThreadingHTTPServer((args.host, args.port), FeedbackHandler)
    print(f"listening on http://{args.host}:{args.port}/ingest", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
