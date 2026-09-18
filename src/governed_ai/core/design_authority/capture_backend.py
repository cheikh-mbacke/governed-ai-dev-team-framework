"""Privileged capture backend for Visual Conformance (Core-owned Protocol).

Adapters implement ``CaptureBackend``. Callers must not inject implementer
observations (DOM/styles/text/screenshots) as truth — only a privileged
backend (or a test double of that Protocol) may produce captures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(slots=True)
class CaptureObservation:
    """Facts produced by a privileged capture backend for one viewport state."""

    screenshot_bytes: bytes | None = None
    dom: dict[str, Any] = field(default_factory=dict)
    styles: dict[str, Any] = field(default_factory=dict)
    text: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CaptureBackend(Protocol):
    """Privileged visual capture surface used by the Conformance Runner."""

    def ensure_ready(self) -> None:
        """Raise if the capture environment cannot run."""

    def configure_workspace(self, workspace: Path, commit_sha: str) -> None:
        """Bind capture to the isolated checkout of the verified commit."""

    def start_application(self, command: list[str]) -> None:
        """Start the application with a Core-approved argv command."""

    def wait_ready(self, readiness: dict[str, Any]) -> None:
        """Wait for the deterministic readiness condition."""

    def open_route(self, route: str) -> None:
        """Navigate to ``route``."""

    def prepare_state(self, state: str, dataset: dict[str, Any] | None = None) -> None:
        """Force the UI into ``state`` (optionally with fixture ``dataset``)."""

    def set_viewport(self, viewport: dict[str, Any]) -> None:
        """Apply viewport geometry / name from the Design Contract."""

    def capture(self) -> CaptureObservation:
        """Return Core-owned observation for the current route/state/viewport."""

    def stop_application(self) -> None:
        """Stop the verifier-owned application process."""


FORBIDDEN_TRUTH_KEYS: frozenset[str] = frozenset(
    {
        "observed_dom",
        "observed_styles",
        "observed_text",
        "observed_components",
        "screenshot_bytes",
        "reference_screenshot_bytes",
        "diff_ratio",
        "allowed_by_tolerance_rule",
        "environment_variance",
    }
)


def strip_forbidden_truth(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Drop caller-supplied fields that must never be treated as verification truth."""
    if not payload:
        return {}
    return {k: v for k, v in payload.items() if k not in FORBIDDEN_TRUTH_KEYS}


def observation_from_mapping(raw: Any) -> CaptureObservation:
    """Normalize a mapping or CaptureObservation into CaptureObservation."""
    if isinstance(raw, CaptureObservation):
        return raw
    if not isinstance(raw, dict):
        raise TypeError("capture backend must return CaptureObservation or mapping")
    text = raw.get("text")
    if text is None:
        text = []
    components = raw.get("components")
    if components is None:
        components = []
    screenshot = raw.get("screenshot_bytes")
    if screenshot is not None and not isinstance(screenshot, (bytes, bytearray)):
        raise TypeError("screenshot_bytes must be bytes")
    return CaptureObservation(
        screenshot_bytes=bytes(screenshot) if screenshot is not None else None,
        dom=dict(raw.get("dom") or {}),
        styles=dict(raw.get("styles") or {}),
        text=[str(t) for t in text],
        components=[str(c) for c in components],
        environment=dict(raw.get("environment") or {}),
    )


class FnCaptureBackend:
    """Test double: wraps a callable as a ``CaptureBackend``.

    The callable receives ``{"route", "state", "viewport", "dataset"}`` and must
    return a ``CaptureObservation`` (or compatible mapping). It is privileged —
    not an implementer observation channel.
    """

    def __init__(self, capture_fn: Callable[[dict[str, Any]], Any]) -> None:
        self._capture_fn = capture_fn
        self._route = ""
        self._state = ""
        self._viewport: dict[str, Any] = {}
        self._dataset: dict[str, Any] | None = None
        self._member_workspaces: dict[str, Path] = {}

    def ensure_ready(self) -> None:
        return None

    def configure_workspace(self, workspace: Path, commit_sha: str) -> None:
        self._workspace = workspace
        self._commit_sha = commit_sha

    def configure_member_workspaces(self, roots: dict[str, Path], commit_sha: str) -> None:
        self._member_workspaces = dict(roots)
        self._commit_sha = commit_sha

    def start_application(self, command: list[str]) -> None:
        self._start_command = list(command)

    def wait_ready(self, readiness: dict[str, Any]) -> None:
        self._readiness = dict(readiness)

    def open_route(self, route: str) -> None:
        self._route = str(route)

    def prepare_state(self, state: str, dataset: dict[str, Any] | None = None) -> None:
        self._state = str(state)
        self._dataset = dataset

    def set_viewport(self, viewport: dict[str, Any]) -> None:
        self._viewport = dict(viewport or {})

    def capture(self) -> CaptureObservation:
        return observation_from_mapping(
            self._capture_fn(
                {
                    "route": self._route,
                    "state": self._state,
                    "viewport": dict(self._viewport),
                    "dataset": self._dataset,
                }
            )
        )

    def stop_application(self) -> None:
        return None


def resolve_capture_backend(
    capture_backend: CaptureBackend | None,
    capture_fn: Callable[[dict[str, Any]], Any] | CaptureBackend | None,
) -> CaptureBackend | None:
    """Prefer ``capture_backend``; treat ``capture_fn`` only as a Protocol double."""
    if capture_backend is not None:
        return capture_backend
    if capture_fn is None:
        return None
    if isinstance(capture_fn, CaptureBackend):
        return capture_fn
    return FnCaptureBackend(capture_fn)
