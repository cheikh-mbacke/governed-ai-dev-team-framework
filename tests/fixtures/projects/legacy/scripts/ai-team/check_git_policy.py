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

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
COMMIT_RE = re.compile(
    r"^(feat|fix|docs|refactor|perf|test|build|ci|chore|revert|style|wip)"
    r"\(WU-[A-Za-z0-9._-]+\)!?:\s+\S.+$"
)
BRANCH_PATTERNS = (
    re.compile(r"^main$"),
    re.compile(r"^wu/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^ai-run/[A-Za-z0-9._-]+/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^integration/[A-Za-z0-9._-]+$"),
    re.compile(r"^hotfix/WU-[A-Za-z0-9._-]+$"),
    re.compile(r"^release/(0|[1-9]\d*)\.(0|[1-9]\d*)$"),
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


def read_product_versions(root: Path = ROOT) -> tuple[str | None, str | None]:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']\s*$', pyproject)
    pyproject_version = match.group(1) if match else None

    framework = json.loads(
        (root / ".ai-team" / "framework-version.json").read_text(encoding="utf-8")
    )
    framework_version = framework.get("version")
    return pyproject_version, framework_version


def validate_versions(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        pyproject_version, framework_version = read_product_versions(root)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot read product version sources: {exc}"]

    if pyproject_version is None:
        errors.append("pyproject.toml does not declare project.version")
    elif not SEMVER_RE.fullmatch(pyproject_version):
        errors.append(f"pyproject.toml version is not SemVer: {pyproject_version!r}")

    if not isinstance(framework_version, str):
        errors.append(".ai-team/framework-version.json does not declare a string version")
    elif not SEMVER_RE.fullmatch(framework_version):
        errors.append(f"framework version is not SemVer: {framework_version!r}")

    if pyproject_version and framework_version and pyproject_version != framework_version:
        errors.append(
            "product version mismatch: "
            f"pyproject.toml={pyproject_version}, framework-version.json={framework_version}"
        )
    return errors


def branch_is_valid(branch: str) -> bool:
    return any(pattern.fullmatch(branch) for pattern in BRANCH_PATTERNS)


def commit_subject_is_valid(subject: str) -> bool:
    return bool(COMMIT_RE.fullmatch(subject))


def validate_branch(branch: str) -> list[str]:
    if branch_is_valid(branch):
        return []
    return [
        f"branch name {branch!r} is not governed; use wu/WU-<ID>-<slug>, "
        "ai-run/<RUN-ID>/<WU-ID>, integration/<RUN-ID>, hotfix/WU-<ID>-<slug>, "
        "or release/<major>.<minor>"
    ]


def validate_commit_range(base: str, head: str = "HEAD", root: Path = ROOT) -> list[str]:
    merge_base = git("merge-base", base, head, root=root)
    commits = git("rev-list", "--reverse", "--no-merges", f"{merge_base}..{head}", root=root)
    errors: list[str] = []
    for sha in commits.splitlines():
        subject = git("show", "-s", "--format=%s", sha, root=root)
        if not commit_subject_is_valid(subject):
            errors.append(
                f"commit {sha[:12]} has invalid subject {subject!r}; "
                "expected type(WU-ID): description"
            )
    return errors


def validate_merge_head(head: str = "HEAD", root: Path = ROOT) -> list[str]:
    parents = git("show", "-s", "--format=%P", head, root=root).split()
    if len(parents) == 2:
        return []
    return [f"protected-branch head {head!r} must be a two-parent merge commit"]


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

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"(?m)^## \[{re.escape(tag_version)}\](?:\s|$)", changelog):
        errors.append(f"CHANGELOG.md has no release section for {tag_version}")
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
        errors.extend(validate_branch(branch))

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
            errors.extend(validate_branch(branch))
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
