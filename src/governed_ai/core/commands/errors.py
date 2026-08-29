"""Stable Command Gateway error codes (Document 12 §9)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    INVALID_SCHEMA = "INVALID_SCHEMA"
    UNAUTHORIZED = "UNAUTHORIZED"
    HUMAN_AUTH_REQUIRED = "HUMAN_AUTH_REQUIRED"
    CONFLICT = "CONFLICT"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    UNSUPPORTED_CONTRACT = "UNSUPPORTED_CONTRACT"
    CAPABILITY_NOT_ENFORCEABLE = "CAPABILITY_NOT_ENFORCEABLE"
    TRANSACTION_RECOVERY_REQUIRED = "TRANSACTION_RECOVERY_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


EXIT_OK = 0
EXIT_CLI = 2
EXIT_SCHEMA = 3
EXIT_UNAUTHORIZED = 4
EXIT_CONFLICT = 5
EXIT_UNSUPPORTED = 6
EXIT_RECOVERY = 7
EXIT_INTERNAL = 10


def exit_code_for(error_code: ErrorCode) -> int:
    if error_code == ErrorCode.INVALID_SCHEMA:
        return EXIT_SCHEMA
    if error_code in {ErrorCode.UNAUTHORIZED, ErrorCode.HUMAN_AUTH_REQUIRED}:
        return EXIT_UNAUTHORIZED
    if error_code in {ErrorCode.CONFLICT, ErrorCode.IDEMPOTENCY_MISMATCH}:
        return EXIT_CONFLICT
    if error_code in {
        ErrorCode.UNSUPPORTED_CONTRACT,
        ErrorCode.CAPABILITY_NOT_ENFORCEABLE,
        ErrorCode.INVALID_TRANSITION,
        ErrorCode.INVARIANT_VIOLATION,
        ErrorCode.NOT_FOUND,
        ErrorCode.ALREADY_EXISTS,
    }:
        return EXIT_SCHEMA
    if error_code == ErrorCode.TRANSACTION_RECOVERY_REQUIRED:
        return EXIT_RECOVERY
    return EXIT_INTERNAL


@dataclass(frozen=True, slots=True)
class GatewayError(Exception):
    code: ErrorCode
    message: str
    path: str | None = None

    def as_dict(self) -> dict[str, str]:
        item: dict[str, str] = {"code": self.code.value, "message": self.message}
        if self.path:
            item["path"] = self.path
        return item
