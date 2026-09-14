"""Security checks for design artifact registration and consumption."""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from governed_ai.core.design_authority.models import (
    APPROVED_REMOTE_SCHEMES,
    FIGMA_HOST_SUFFIXES,
    MAX_ARTIFACT_BYTES,
    MAX_REMOTE_URL_LENGTH,
    SUPPORTED_LOCAL_EXTENSIONS,
)

SVG_SCRIPT_PATTERN = re.compile(
    r"<\s*script\b|javascript:|xlink:href\s*=\s*[\"']\s*https?:|"
    r"<\s*foreignObject\b|<\s*iframe\b|on\w+\s*=",
    re.IGNORECASE,
)
HTML_ACTIVE_PATTERN = re.compile(
    r"<\s*script\b|javascript:|<\s*iframe\b|<\s*object\b|<\s*embed\b|on\w+\s*=",
    re.IGNORECASE,
)


class DesignSecurityError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def assert_relative_workspace_path(workspace_root: Path, path: str) -> Path:
    text = str(path).replace("\\", "/").strip()
    if not text:
        raise DesignSecurityError("empty_path", "path is empty")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise DesignSecurityError(
            "absolute_path_outside_workspace",
            f"absolute paths are forbidden: {path}",
        )
    if ".." in Path(text).parts:
        raise DesignSecurityError(
            "forbidden_path_traversal",
            f"path traversal forbidden: {path}",
        )
    absolute = (workspace_root / text).resolve()
    try:
        absolute.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise DesignSecurityError(
            "absolute_path_outside_workspace",
            f"resolved path escapes workspace: {path}",
        ) from exc
    return absolute


def assert_no_escaping_link(workspace_root: Path, path: str) -> None:
    text = str(path).replace("\\", "/").strip()
    absolute = workspace_root / text
    if not absolute.exists():
        return
    root = workspace_root.resolve()
    try:
        resolved = absolute.resolve()
        resolved.relative_to(root)
    except ValueError as exc:
        raise DesignSecurityError(
            "escaping_symlink_or_junction",
            f"symlink/junction escapes workspace: {path}",
        ) from exc
    if absolute.is_symlink():
        target = Path(os.readlink(absolute))
        if not target.is_absolute():
            target = (absolute.parent / target).resolve()
        else:
            target = target.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise DesignSecurityError(
                "escaping_symlink_or_junction",
                f"symlink/junction target escapes workspace: {path}",
            ) from exc


def assert_file_size(path: Path, *, max_bytes: int = MAX_ARTIFACT_BYTES) -> int:
    size = path.stat().st_size
    if size > max_bytes:
        raise DesignSecurityError(
            "artifact_too_large",
            f"artifact exceeds {max_bytes} bytes",
            details={"size_bytes": size, "max_bytes": max_bytes},
        )
    return size


def detect_source_type(path: Path, *, declared: str | None = None) -> str:
    if declared and declared != "other":
        return declared
    ext = path.suffix.lower()
    return SUPPORTED_LOCAL_EXTENSIONS.get(ext, "other")


def assert_mime_coherent(path: Path, source_type: str) -> str | None:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed is None:
        return None
    expected_prefixes = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "svg": "image/svg",
        "pdf": "application/pdf",
        "html_static": "text/html",
        "tokens_json": "application/json",
        "markdown_spec": "text/",
        "screenshot": "image/",
        "wireframe": "image/",
    }
    expected = expected_prefixes.get(source_type)
    if expected and not guessed.startswith(expected.rstrip("*")):
        if source_type in {"screenshot", "wireframe", "markdown_spec"}:
            return guessed
        raise DesignSecurityError(
            "mime_type_mismatch",
            f"MIME {guessed!r} inconsistent with source_type {source_type!r}",
            details={"path": str(path), "mime": guessed, "source_type": source_type},
        )
    return guessed


def assert_svg_safe(content: bytes | str) -> None:
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    if SVG_SCRIPT_PATTERN.search(text):
        raise DesignSecurityError(
            "unsafe_svg_content",
            "SVG contains scripts, handlers, or external references",
        )


def assert_html_static_safe(content: bytes | str) -> None:
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    if HTML_ACTIVE_PATTERN.search(text):
        raise DesignSecurityError(
            "unsafe_html_mockup",
            "HTML mockup contains active/script content",
        )


def assert_remote_uri_allowed(
    uri: str,
    *,
    allow_figma: bool = True,
    approved_hosts: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    text = str(uri or "").strip()
    if not text:
        raise DesignSecurityError("empty_remote_uri", "remote URI is empty")
    if len(text) > MAX_REMOTE_URL_LENGTH:
        raise DesignSecurityError("remote_uri_too_long", "remote URI exceeds max length")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in APPROVED_REMOTE_SCHEMES:
        raise DesignSecurityError(
            "unapproved_remote_scheme",
            f"scheme {scheme!r} is not approved for design references",
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise DesignSecurityError("invalid_remote_uri", "remote URI missing host")
    approved = {h.lower() for h in (approved_hosts or [])}
    is_figma = any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in FIGMA_HOST_SUFFIXES)
    if is_figma:
        if not allow_figma:
            raise DesignSecurityError(
                "figma_not_enabled",
                "Figma links are not enabled for this project",
            )
        return {"kind": "figma_link", "host": host, "uri": text}
    if approved and host not in approved:
        raise DesignSecurityError(
            "unapproved_remote_host",
            f"host {host!r} is not on the approved remote list",
            details={"host": host},
        )
    if not approved and not is_figma:
        raise DesignSecurityError(
            "unapproved_remote_host",
            f"remote host {host!r} requires explicit approval before becoming authoritative",
            details={"host": host},
        )
    return {"kind": "https", "host": host, "uri": text}


def validate_local_artifact(
    workspace_root: Path,
    relative_path: str,
    *,
    source_type: str | None = None,
) -> dict:
    """Validate a local design file and return security metadata."""
    absolute = assert_relative_workspace_path(workspace_root, relative_path)
    assert_no_escaping_link(workspace_root, relative_path)
    if not absolute.is_file():
        raise DesignSecurityError("artifact_not_found", f"artifact not found: {relative_path}")
    size = assert_file_size(absolute)
    detected = detect_source_type(absolute, declared=source_type)
    mime = assert_mime_coherent(absolute, detected)
    content = absolute.read_bytes()
    if detected == "svg":
        assert_svg_safe(content)
    if detected == "html_static":
        assert_html_static_safe(content)
    return {
        "absolute_path": absolute,
        "source_type": detected,
        "size_bytes": size,
        "mime_type": mime,
        "content": content,
    }
