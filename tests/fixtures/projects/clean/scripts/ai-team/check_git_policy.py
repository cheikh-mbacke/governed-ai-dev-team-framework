#!/usr/bin/env python3
"""Validate repository Git, commit, branch, version, and release conventions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
COMMIT_RE = re.compile(
    r"^(feat|fix|docs|refactor|perf|test|build|ci|chore|revert|style|wip)"
    r"\(WU-[A-Za-z0-9._-]+\)!?:\s+\S.+$"
)
FABRICATION_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|refactor|perf|test|build|ci|chore|revert|style|wip)"
    r"(!?)?:\s+\S.+$"
)
BRANCH_PATTERNS = (
    re.compile(r"^main$"),
    re.compile(r"^wu/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^ai-run/[A-Za-z0-9._-]+/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^integration/[A-Za-z0-9._-]+$"),
    re.compile(r"^hotfix/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^release/(0|[1-9]\d*)\.(0|[1-9]\d*)$"),
)
FABRICATION_BRANCH_PATTERNS = (
    re.compile(r"^main$"),
    re.compile(r"^renov/.+$"),
    re.compile(r"^fix/.+$"),
    re.compile(r"^feat/.+$"),
    re.compile(r"^docs/.+$"),
    re.compile(r"^chore/.+$"),
    re.compile(r"^release/(0|[1-9]\d*)\.(0|[1-9]\d*)$"),
)
CHANGELOG_PLACEHOLDER_RE = re.compile(
    r"non\s+publi[eé]e|unreleased|tbd|à\s+d[eé]terminer|pending",
    re.IGNORECASE,
)
TAG_SIGNATURE_MARKERS = (
    "gpgsig",
    "-----BEGIN PGP SIGNATURE-----",
    "-----BEGIN SSH SIGNATURE-----",
)


def git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _profile_path(root: Path) -> Path | None:
    for path in (
        root / ".fabric" / "project-profile.yaml",
        root / ".ai-team" / "project-profile.yaml",
    ):
        if path.is_file():
            return path
    return None


def _framework_version_path(root: Path) -> Path:
    fabric = root / ".fabric" / "framework-version.json"
    return fabric if fabric.is_file() else root / ".ai-team" / "framework-version.json"


def read_repository_kind(root: Path = ROOT) -> str | None:
    profile = _profile_path(root)
    if profile is None:
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


def is_framework_source_repo(root: Path = ROOT) -> bool:
    return read_repository_kind(root) == "framework_source"


def read_product_versions(root: Path = ROOT) -> tuple[str | None, str | None]:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']\s*$', pyproject)
    pyproject_version = match.group(1) if match else None

    framework = json.loads(_framework_version_path(root).read_text(encoding="utf-8"))
    framework_version = framework.get("version")
    return pyproject_version, framework_version


def validate_versions(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if read_repository_kind(root) == "existing_or_greenfield_project":
        # pyproject.toml is the framework's own canonical_version_source; an
        # installed client project may use any stack (see the "adapt: ..."
        # note on distribution/payload/.ai-team/constitution/95-git-release-
        # policy.yaml canonical_version_source) and has no reason to declare
        # one, let alone keep it equal to the framework's own version.
        return errors
    try:
        pyproject_version, framework_version = read_product_versions(root)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot read product version sources: {exc}"]

    if pyproject_version is None:
        errors.append("pyproject.toml does not declare project.version")
    elif not SEMVER_RE.fullmatch(pyproject_version):
        errors.append(f"pyproject.toml version is not SemVer: {pyproject_version!r}")

    if not isinstance(framework_version, str):
        version_label = _framework_version_path(root).relative_to(root).as_posix()
        errors.append(f"{version_label} does not declare a string version")
    elif not SEMVER_RE.fullmatch(framework_version):
        errors.append(f"framework version is not SemVer: {framework_version!r}")

    if pyproject_version and framework_version and pyproject_version != framework_version:
        errors.append(
            "product version mismatch: "
            f"pyproject.toml={pyproject_version}, framework-version.json={framework_version}"
        )

    manifest_path = root / "adapters" / "cursor" / "manifest.json"
    if pyproject_version and manifest_path.is_file():
        try:
            descriptor = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read adapters/cursor/manifest.json: {exc}")
        else:
            if isinstance(descriptor, dict):
                if str(ROOT) not in sys.path:
                    sys.path.insert(0, str(ROOT))
                from distribution.installer.version_policy import (
                    validate_adapter_descriptor_alignment,
                )

                errors.extend(
                    validate_adapter_descriptor_alignment(
                        pyproject_version,
                        "cursor",
                        descriptor,
                    )
                )
    if is_framework_source_repo(root):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        src_root = root / "src"
        if src_root.is_dir() and str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))
        from distribution.installer.version_policy import validate_release_matrix

        errors.extend(validate_release_matrix(root))
    return errors


def branch_is_valid(branch: str, root: Path = ROOT) -> bool:
    patterns = FABRICATION_BRANCH_PATTERNS if is_framework_source_repo(root) else BRANCH_PATTERNS
    return any(pattern.fullmatch(branch) for pattern in patterns)


def commit_subject_is_valid(subject: str, root: Path = ROOT) -> bool:
    if is_framework_source_repo(root):
        return bool(FABRICATION_COMMIT_RE.fullmatch(subject))
    return bool(COMMIT_RE.fullmatch(subject))


def validate_branch(branch: str, root: Path = ROOT) -> list[str]:
    if branch_is_valid(branch, root):
        return []
    if is_framework_source_repo(root):
        return [
            f"branch name {branch!r} is not allowed on framework_source; use "
            "renov/<slug>, fix/<slug>, feat/<slug>, docs/<slug>, chore/<slug>, "
            "or release/<major>.<minor>"
        ]
    return [
        f"branch name {branch!r} is not governed; use wu/WU-<ID>-<slug>, "
        "ai-run/<RUN-ID>/<WU-ID>, integration/<RUN-ID>, hotfix/WU-<ID>-<slug>, "
        "or release/<major>.<minor>"
    ]


def validate_commit_range(base: str, head: str = "HEAD", root: Path = ROOT) -> list[str]:
    merge_base = git("merge-base", base, head, root=root)
    commits = git("rev-list", "--reverse", "--no-merges", f"{merge_base}..{head}", root=root)
    errors: list[str] = []
    expected = (
        "expected type: description (Conventional Commits)"
        if is_framework_source_repo(root)
        else "expected type(WU-ID): description"
    )
    for sha in commits.splitlines():
        subject = git("show", "-s", "--format=%s", sha, root=root)
        if not commit_subject_is_valid(subject, root):
            errors.append(
                f"commit {sha[:12]} has invalid subject {subject!r}; {expected}"
            )
    return errors


def validate_merge_head(head: str = "HEAD", root: Path = ROOT) -> list[str]:
    parents = git("show", "-s", "--format=%P", head, root=root).split()
    if len(parents) == 2:
        return []
    return [f"protected-branch head {head!r} must be a two-parent merge commit"]


def tag_payload_declares_signature(payload: str) -> bool:
    """Return True when an annotated tag payload includes a signature block."""
    return any(marker in payload for marker in TAG_SIGNATURE_MARKERS)


def validate_changelog_release_section(tag_version: str, changelog: str) -> list[str]:
    """Require a publish-ready Keep a Changelog header for a tagged release."""
    errors: list[str] = []
    header = re.search(
        rf"(?m)^## \[{re.escape(tag_version)}\]\s*-\s*(.+)$",
        changelog,
    )
    if not header:
        errors.append(
            f"CHANGELOG.md must declare ## [{tag_version}] - YYYY-MM-DD before tagging"
        )
        return errors

    date_part = header.group(1).strip()
    if CHANGELOG_PLACEHOLDER_RE.search(date_part):
        errors.append(
            "CHANGELOG.md release "
            f"{tag_version} is not publish-ready (placeholder date: {date_part!r})"
        )
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part):
        errors.append(
            "CHANGELOG.md release "
            f"{tag_version} must use ISO date YYYY-MM-DD, got {date_part!r}"
        )
    return errors


def validate_tag_signature(tag: str, root: Path = ROOT) -> list[str]:
    """Require an annotated tag that declares a GPG or SSH signature."""
    errors: list[str] = []
    verify = subprocess.run(
        ["git", "verify-tag", tag],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if verify.returncode == 0:
        return errors

    payload = git("cat-file", "-p", f"refs/tags/{tag}", root=root, check=False)
    if payload and tag_payload_declares_signature(payload):
        return errors

    detail = (verify.stderr or verify.stdout or "missing or unsigned tag").strip()
    errors.append(
        f"release tag {tag!r} must be annotated and signed (git tag -s); {detail}"
    )
    return errors


def validate_release_tag(tag: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    match = re.fullmatch(r"v(.+)", tag)
    if not match or not SEMVER_RE.fullmatch(match.group(1)):
        return [f"release tag {tag!r} must use vMAJOR.MINOR.PATCH SemVer format"]

    pyproject_version, framework_version = read_product_versions(root)
    tag_version = match.group(1)
    if pyproject_version != tag_version or framework_version != tag_version:
        errors.append(
            f"tag {tag!r} does not match product version sources "
            f"({pyproject_version!r}, {framework_version!r})"
        )

    object_type = git("cat-file", "-t", f"refs/tags/{tag}", root=root, check=False)
    if object_type != "tag":
        errors.append(f"release tag {tag!r} must be an annotated tag, got {object_type or 'missing'}")
        return errors

    errors.extend(validate_tag_signature(tag, root=root))

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    errors.extend(validate_changelog_release_section(tag_version, changelog))
    return errors


def _object_exists(ref: str, root: Path = ROOT) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return completed.returncode == 0


def validate_ci_environment(root: Path = ROOT) -> list[str]:
    errors = validate_versions(root)
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")

    if ref_type == "tag":
        errors.extend(validate_release_tag(ref_name, root))
        return errors

    branch = os.environ.get("GITHUB_HEAD_REF") or ref_name
    if branch:
        errors.extend(validate_branch(branch, root))

    if event_name == "pull_request":
        base_branch = os.environ.get("GITHUB_BASE_REF")
        if not base_branch:
            errors.append("GITHUB_BASE_REF is missing for pull_request event")
        else:
            errors.extend(validate_commit_range(f"origin/{base_branch}", "HEAD", root))
        return errors

    if event_name == "push":
        before = ""
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path:
            try:
                before = str(json.loads(Path(event_path).read_text(encoding="utf-8")).get("before", ""))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f"cannot read GitHub event payload: {exc}")
        if before and set(before) != {"0"} and _object_exists(before, root):
            errors.extend(validate_commit_range(before, "HEAD", root))
        if branch == "main":
            errors.extend(validate_merge_head("HEAD", root))
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="derive checks from GitHub Actions")
    parser.add_argument("--base-ref", help="validate non-merge commits since this ref")
    parser.add_argument("--head-ref", default="HEAD", help="head ref used with --base-ref")
    parser.add_argument("--tag", help="validate a release tag")
    parser.add_argument(
        "--require-merge-head", action="store_true", help="require HEAD to be a merge commit"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.ci:
            errors = validate_ci_environment(ROOT)
        else:
            errors = validate_versions(ROOT)
            branch = git("rev-parse", "--abbrev-ref", "HEAD")
            errors.extend(validate_branch(branch, ROOT))
            if args.base_ref:
                errors.extend(validate_commit_range(args.base_ref, args.head_ref, ROOT))
            if args.tag:
                errors.extend(validate_release_tag(args.tag, ROOT))
            if args.require_merge_head:
                errors.extend(validate_merge_head(args.head_ref, ROOT))
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        errors = [str(exc)]

    if errors:
        print("Git policy validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Git policy validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
