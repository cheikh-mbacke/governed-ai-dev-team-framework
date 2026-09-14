"""Governed Verification Runner — independent command execution after the agent."""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from governed_ai.core.execution_gateway.contracts import SCHEMA_VERSION, CheckResult
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.execution_gateway.security import assert_command_allowed, redact_secrets

PROFILE_COMMAND_FIELDS = (
    "lint",
    "unit_test",
    "integration_test",
    "build",
)

_MAX_TRANSCRIPT_CHARS = 32_000


def _hash_transcript(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8', errors='replace')).hexdigest()}"


def compile_command_argv(command: str) -> list[str]:
    """Compile a profile command string into a structured argv (no shell)."""
    text = str(command or "").strip()
    if not text:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message="empty verification command",
                path="verification.command",
            )
        )
    try:
        argv = shlex.split(text, posix=os.name != "nt")
    except ValueError as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message=f"command could not be parsed into argv: {exc}",
                path="verification.command",
            )
        ) from exc
    if not argv:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message="empty argv after parse",
                path="verification.command",
            )
        )
    # Normalize bare "python" to the current interpreter for portable tests.
    if argv[0] in {"python", "python3"}:
        argv = [sys.executable, *argv[1:]]
    return argv


def run_verification_command(
    *,
    workspace_root: Path,
    command: str,
    allowlist: list[str] | tuple[str, ...] | None,
    timeout_seconds: float,
    secrets_to_redact: list[str] | tuple[str, ...] | None = None,
    canonical_check_id: str,
    env: dict[str, str] | None = None,
    allow_empty_allowlist: bool = False,
) -> CheckResult:
    assert_command_allowed(
        command,
        allowlist,
        allow_empty_allowlist=allow_empty_allowlist,
    )
    argv = compile_command_argv(command)
    cleaned_env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
    if env:
        cleaned_env.update(env)
    for key in list(cleaned_env):
        upper = key.upper()
        if any(token in upper for token in ("SECRET", "TOKEN", "PASSWORD", "API_KEY")):
            if env is None or key not in env:
                cleaned_env.pop(key, None)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=max(0.1, timeout_seconds),
            check=False,
            env=cleaned_env,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        transcript = redact_secrets(
            (stdout + "\n" + stderr)[:_MAX_TRANSCRIPT_CHARS],
            secrets_to_redact,
        )
        return CheckResult(
            schema_version=SCHEMA_VERSION,
            canonical_id=canonical_check_id,
            reported_name=canonical_check_id,
            status="timed_out",
            blocking=True,
            trust_level="framework_verified",
            evidence_ref=None,
            verifier="verification_runner",
            exit_code=None,
            duration_ms=duration_ms,
            transcript_hash=_hash_transcript(transcript),
            limitations=["command timed out"],
        )
    except OSError as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="verification_exec_failed",
                message=str(exc),
                path="verification.command",
            )
        ) from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    transcript = redact_secrets(
        ((completed.stdout or "") + "\n" + (completed.stderr or ""))[:_MAX_TRANSCRIPT_CHARS],
        secrets_to_redact,
    )
    status = "passed" if completed.returncode == 0 else "failed"
    return CheckResult(
        schema_version=SCHEMA_VERSION,
        canonical_id=canonical_check_id,
        reported_name=canonical_check_id,
        status=status,
        blocking=True,
        trust_level="framework_verified",
        evidence_ref=None,
        verifier="verification_runner",
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        transcript_hash=_hash_transcript(transcript),
        limitations=[] if status == "passed" else ["non-zero exit"],
    )


def run_profile_verifications(
    *,
    workspace_root: Path,
    profile_commands: dict[str, str | None],
    allowlist: list[str] | tuple[str, ...] | None,
    timeout_seconds: float = 60.0,
    secrets_to_redact: list[str] | tuple[str, ...] | None = None,
    fields: tuple[str, ...] = PROFILE_COMMAND_FIELDS,
    allow_empty_allowlist: bool = False,
) -> list[CheckResult]:
    """Execute configured project-profile commands independently of the agent."""
    field_to_check = {
        "lint": "lint",
        "unit_test": "tests",
        "integration_test": "tests",
        "build": "build",
    }
    results: list[CheckResult] = []
    for field in fields:
        command = profile_commands.get(field)
        if not command:
            continue
        canonical = field_to_check.get(field, field)
        results.append(
            run_verification_command(
                workspace_root=workspace_root,
                command=str(command),
                allowlist=allowlist,
                timeout_seconds=timeout_seconds,
                secrets_to_redact=secrets_to_redact,
                canonical_check_id=canonical,
                allow_empty_allowlist=allow_empty_allowlist,
            )
        )
    return results


def load_profile_commands(profile: dict[str, Any]) -> dict[str, str | None]:
    commands = profile.get("commands") or {}
    return {field: commands.get(field) for field in PROFILE_COMMAND_FIELDS}
