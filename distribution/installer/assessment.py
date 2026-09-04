"""Adoption assessment — read-only pre-install conflict inventory (Documents 19–20)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.collisions import (
    LEGACY_FRAMEWORK_FINGERPRINTS,
    _legacy_framework_install_fingerprint,
)
from distribution.installer.fabrication_layout import (
    FRAMEWORK_SOURCE_KIND,
    read_repository_kind,
)
from distribution.installer.record import INSTALLATION_RECORD_FILE

SCHEMA_VERSION = 1
REPORT_KIND = "adoption_assessment_report"

CATEGORIES = (
    "engagement",
    "authority",
    "artifact",
    "prerequisite",
    "baseline",
    "remodel",
)

# Heuristic roots that usually mean "existing product code" on a brownfield target.
_CODE_ROOT_CANDIDATES = (
    "src",
    "app",
    "lib",
    "libs",
    "packages",
    "backend",
    "frontend",
    "server",
    "client",
    "cmd",
    "internal",
    "pkg",
)

_PRODUCT_DOC_CANDIDATES = (
    "docs/product",
)

SEVERITIES = frozenset({"blocking", "warning", "info"})
RESOLUTION_STATUSES = frozenset(
    {
        "eliminate",
        "remap",
        "waive",
        "defer_blocks_adoption",
        "unresolved",
    }
)
RESOLVED_BLOCKING = frozenset({"eliminate", "remap", "waive"})
VERDICTS = frozenset({"go", "go_with_backlog", "no_go"})

# Human-facing resolution options — never include a "keep hybrid authority" choice.
DEFAULT_RESOLUTION_OPTIONS = [
    "eliminate",
    "remap",
    "waive",
    "defer_blocks_adoption",
]

ASSESSMENT_SKIP_ENV = "GOVERNED_AI_SKIP_ASSESSMENT_GATE"


@dataclass
class Finding:
    id: str
    category: str
    severity: str
    summary: str
    evidence: dict[str, Any]
    resolution_options: list[str] = field(default_factory=lambda: list(DEFAULT_RESOLUTION_OPTIONS))
    resolution_status: str = "unresolved"
    waiver_authorization_id: str | None = None
    operator_confirmation_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def blocking_is_resolved(finding: Finding) -> bool:
    if finding.severity != "blocking":
        return True
    if finding.resolution_status == "defer_blocks_adoption":
        return False
    if finding.resolution_status not in RESOLVED_BLOCKING:
        return False
    if finding.resolution_status == "waive":
        return bool(finding.waiver_authorization_id)
    return True


def compute_verdict(findings: list[Finding]) -> str:
    open_blocking = [f for f in findings if f.severity == "blocking" and not blocking_is_resolved(f)]
    if open_blocking:
        return "no_go"
    warnings_open = [
        f
        for f in findings
        if f.severity == "warning" and f.resolution_status in {"unresolved", "defer_blocks_adoption"}
    ]
    if warnings_open:
        return "go_with_backlog"
    return "go"


def apply_resolutions(findings: list[Finding], resolutions: dict[str, Any] | None) -> list[Finding]:
    if not resolutions:
        return findings
    per_finding = resolutions.get("findings") or {}
    if not isinstance(per_finding, dict):
        raise ValueError("resolutions.findings must be an object keyed by finding id")
    updated: list[Finding] = []
    for finding in findings:
        patch = per_finding.get(finding.id)
        if not patch:
            updated.append(finding)
            continue
        if not isinstance(patch, dict):
            raise ValueError(f"resolutions.findings[{finding.id!r}] must be an object")
        status = patch.get("resolution_status", finding.resolution_status)
        if status not in RESOLUTION_STATUSES:
            raise ValueError(f"invalid resolution_status for {finding.id}: {status!r}")
        auth = patch.get("waiver_authorization_id", finding.waiver_authorization_id)
        if auth is not None:
            auth = str(auth) or None
        updated.append(
            Finding(
                id=finding.id,
                category=finding.category,
                severity=finding.severity,
                summary=finding.summary,
                evidence={**finding.evidence, **(patch.get("evidence") or {})},
                resolution_options=list(finding.resolution_options),
                resolution_status=str(status),
                waiver_authorization_id=auth,
                operator_confirmation_required=finding.operator_confirmation_required,
            )
        )
    return updated


def _finding(
    *,
    id: str,
    category: str,
    severity: str,
    summary: str,
    evidence: dict[str, Any] | None = None,
    operator_confirmation_required: bool = False,
    resolution_options: list[str] | None = None,
) -> Finding:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")
    return Finding(
        id=id,
        category=category,
        severity=severity,
        summary=summary,
        evidence=evidence or {},
        resolution_options=list(resolution_options or DEFAULT_RESOLUTION_OPTIONS),
        operator_confirmation_required=operator_confirmation_required,
    )


def _scan_engagement(target: Path) -> list[Finding]:
    return [
        _finding(
            id="engagement.exclusive_governance",
            category="engagement",
            severity="blocking",
            summary=(
                "Human operators must accept exclusive governance before adoption "
                "(no concurrent unresolved authority)."
            ),
            evidence={"principle": "Document 19 §2–§3", "target": str(target)},
            operator_confirmation_required=True,
            resolution_options=["remap", "defer_blocks_adoption"],
        ),
        _finding(
            id="engagement.human_authorities",
            category="engagement",
            severity="blocking",
            summary=(
                "Name human authorities (product, engineering constitution, "
                "production release, final acceptance) before production use."
            ),
            evidence={"project_profile_fields": ["human_authorities.*"]},
            operator_confirmation_required=True,
            resolution_options=["remap", "defer_blocks_adoption"],
        ),
    ]


def _scan_authority(target: Path) -> list[Finding]:
    findings: list[Finding] = []
    git_dir = target / ".git"
    if git_dir.exists():
        findings.append(
            _finding(
                id="authority.git_present",
                category="authority",
                severity="info",
                summary="Git repository detected; confirm client git policy remap before adoption.",
                evidence={"path": ".git"},
                operator_confirmation_required=True,
            )
        )
    else:
        findings.append(
            _finding(
                id="authority.git_missing",
                category="authority",
                severity="warning",
                summary=(
                    "Target is not a Git repository; transactional updates are weaker. "
                    "Initialize Git or accept the limitation."
                ),
                evidence={"path": ".git", "exists": False},
            )
        )

    ci_markers = [
        ".github/workflows",
        ".gitlab-ci.yml",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        "Jenkinsfile",
    ]
    present_ci = [rel for rel in ci_markers if (target / rel).exists()]
    if present_ci:
        findings.append(
            _finding(
                id="authority.ci_markers",
                category="authority",
                severity="warning",
                summary=(
                    "CI/CD configuration detected; confirm compatibility with governed "
                    "branch and merge rules (no silent bypass of gates)."
                ),
                evidence={"paths": present_ci},
                operator_confirmation_required=True,
            )
        )
    else:
        findings.append(
            _finding(
                id="authority.ci_none_detected",
                category="authority",
                severity="info",
                summary="No common CI config markers detected automatically.",
                evidence={"checked": ci_markers},
            )
        )

    findings.append(
        _finding(
            id="authority.concurrent_orchestrators",
            category="authority",
            severity="warning",
            summary=(
                "Operators must confirm there is no concurrent agent orchestrator or bot "
                "mutating project state outside the Command Gateway."
            ),
            evidence={"automatic_detection": "not_available_v1"},
            operator_confirmation_required=True,
        )
    )
    return findings


def _scan_artifacts(target: Path) -> list[Finding]:
    findings: list[Finding] = []
    has_record = (target / INSTALLATION_RECORD_FILE).is_file()

    fingerprint = _legacy_framework_install_fingerprint(target)
    if fingerprint is not None:
        findings.append(
            _finding(
                id="artifact.legacy_framework_layout",
                category="artifact",
                severity="blocking",
                summary=(
                    "Pre-0.7.0 framework layout fingerprint detected; use "
                    "`tools/install.py --update`, not a fresh install."
                ),
                evidence={"fingerprint": fingerprint},
                resolution_options=["remap", "defer_blocks_adoption"],
            )
        )

    cursor_dir = target / ".cursor"
    if cursor_dir.exists() and not has_record:
        evidence: dict[str, Any] = {"path": ".cursor", "is_dir": cursor_dir.is_dir()}
        cli_json = cursor_dir / "cli.json"
        if cli_json.is_file():
            evidence["cli_json"] = ".cursor/cli.json"
            findings.append(
                _finding(
                    id="artifact.cursor_cli_json",
                    category="artifact",
                    severity="blocking",
                    summary=(
                        "Existing `.cursor/cli.json` will collide with the Cursor adapter "
                        "on fresh install; eliminate, remap content, or waive with trace."
                    ),
                    evidence={"path": ".cursor/cli.json"},
                )
            )
        findings.append(
            _finding(
                id="artifact.cursor_tree",
                category="artifact",
                severity="blocking",
                summary=(
                    "Existing `.cursor/` tree without an installation record; fresh install "
                    "will not overwrite without `--force` and would replace adapter-managed files."
                ),
                evidence=evidence,
            )
        )

    agents = target / "AGENTS.md"
    if agents.is_file() and not has_record:
        findings.append(
            _finding(
                id="artifact.agents_md",
                category="artifact",
                severity="warning",
                summary=(
                    "Existing AGENTS.md will be merged via governed-ai markers; review for "
                    "conflicting instructions."
                ),
                evidence={"path": "AGENTS.md"},
            )
        )

    scripts_ai = target / "scripts" / "ai-team"
    if scripts_ai.is_dir() and not has_record and any(scripts_ai.rglob("*")):
        findings.append(
            _finding(
                id="artifact.scripts_ai_team",
                category="artifact",
                severity="blocking",
                summary=(
                    "Non-empty `scripts/ai-team/` without installation record; collision risk "
                    "on fresh install."
                ),
                evidence={"path": "scripts/ai-team"},
            )
        )

    if has_record:
        findings.append(
            _finding(
                id="artifact.already_installed",
                category="artifact",
                severity="info",
                summary="Installation record present; prefer `--update` over fresh install.",
                evidence={"path": INSTALLATION_RECORD_FILE.as_posix()},
            )
        )

    return findings


def _scan_prerequisites(target: Path, *, source_root: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []

    if source_root is not None and target.resolve() == source_root.resolve():
        findings.append(
            _finding(
                id="prerequisite.target_is_framework_source_root",
                category="prerequisite",
                severity="blocking",
                summary="Target is the framework source repository root; choose another directory.",
                evidence={"target": str(target)},
                resolution_options=["defer_blocks_adoption"],
            )
        )

    kind = read_repository_kind(target)
    if kind == FRAMEWORK_SOURCE_KIND:
        findings.append(
            _finding(
                id="prerequisite.repository_kind_framework_source",
                category="prerequisite",
                severity="blocking",
                summary="Target declares repository_kind framework_source; not an adoptant install target.",
                evidence={"repository_kind": kind},
                resolution_options=["defer_blocks_adoption"],
            )
        )

    py_major, py_minor = sys.version_info[:2]
    if (py_major, py_minor) < (3, 10):
        findings.append(
            _finding(
                id="prerequisite.python_version",
                category="prerequisite",
                severity="blocking",
                summary=f"Python >= 3.10 required; runner is {py_major}.{py_minor}.",
                evidence={"python_version": f"{py_major}.{py_minor}.{sys.version_info[2]}"},
            )
        )
    else:
        findings.append(
            _finding(
                id="prerequisite.python_version",
                category="prerequisite",
                severity="info",
                summary=f"Python {py_major}.{py_minor} satisfies the >= 3.10 requirement.",
                evidence={"python_version": f"{py_major}.{py_minor}.{sys.version_info[2]}"},
            )
        )

    if not target.exists():
        findings.append(
            _finding(
                id="prerequisite.target_missing",
                category="prerequisite",
                severity="warning",
                summary="Target path does not exist yet; install may create it.",
                evidence={"path": str(target)},
            )
        )
    elif not os.access(target, os.W_OK):
        findings.append(
            _finding(
                id="prerequisite.target_not_writable",
                category="prerequisite",
                severity="blocking",
                summary="Target directory is not writable.",
                evidence={"path": str(target)},
            )
        )
    else:
        findings.append(
            _finding(
                id="prerequisite.target_writable",
                category="prerequisite",
                severity="info",
                summary="Target directory is writable.",
                evidence={"path": str(target)},
            )
        )

    findings.append(
        _finding(
            id="prerequisite.cursor_adapter_only",
            category="prerequisite",
            severity="info",
            summary="Only the Cursor adapter is shipped in 0.7.x; confirm Cursor is the intended tool.",
            evidence={"active_adapter_expected": "cursor"},
            operator_confirmation_required=True,
        )
    )
    return findings


def _existing_code_roots(target: Path) -> list[str]:
    """Return relative paths that look like non-empty application/source trees."""
    found: list[str] = []
    for name in _CODE_ROOT_CANDIDATES:
        root = target / name
        if not root.is_dir():
            continue
        if any(path.is_file() for path in root.rglob("*")):
            found.append(name)
    return found


def _product_doc_roots(target: Path) -> list[str]:
    found: list[str] = []
    for rel in _PRODUCT_DOC_CANDIDATES:
        path = target / rel
        if path.is_dir() and any(path.rglob("*")):
            found.append(rel)
    return found


def _scan_baseline(target: Path) -> list[Finding]:
    """Brownfield readiness signals: human material + as-built gaps before compile.

    Assessment does not invent product intent from the repository. It forces an
    explicit human commitment: sufficient authoritative material, plus an inventory
    of legacy / out-of-scope / cleanup work, before the first `/compile-project`.
    """
    findings: list[Finding] = []
    code_roots = _existing_code_roots(target) if target.is_dir() else []
    product_docs = _product_doc_roots(target) if target.is_dir() else []

    findings.append(
        _finding(
            id="baseline.repository_is_observed_reality",
            category="baseline",
            severity="info",
            summary=(
                "Repository content is observed reality, not product authority. "
                "Gaps versus human intent must be reported, never used to rewrite intent."
            ),
            evidence={"constitution": "00-authority.yaml#repository_vs_intent"},
        )
    )

    if not code_roots:
        findings.append(
            _finding(
                id="baseline.greenfield_or_minimal_code",
                category="baseline",
                severity="info",
                summary=(
                    "No common application source roots detected; treat as greenfield-like "
                    "for as-built inventory (still require human product material before compile)."
                ),
                evidence={"checked_roots": list(_CODE_ROOT_CANDIDATES)},
            )
        )
        findings.append(
            _finding(
                id="baseline.human_material_before_compile",
                category="baseline",
                severity="warning",
                summary=(
                    "Before G0 / `/compile-project`, register authoritative product sources "
                    "with enough precision for the first scope (Definition of Ready). "
                    "Remap = commit to produce that material before compile."
                ),
                evidence={"phase": "post_install_pre_compile"},
                operator_confirmation_required=True,
                resolution_options=["remap", "defer_blocks_adoption"],
            )
        )
        return findings

    findings.append(
        _finding(
            id="baseline.existing_code_detected",
            category="baseline",
            severity="info",
            summary="Existing application/source trees detected; brownfield baseline applies.",
            evidence={"code_roots": code_roots},
        )
    )

    findings.append(
        _finding(
            id="baseline.as_built_inventory",
            category="baseline",
            severity="warning",
            summary=(
                "Before first compile, inventory as-built reality against intended product: "
                "conformance gaps, out-of-scope surfaces, and cleanup/remediation that must "
                "become explicit Work Units — not silent assumptions. "
                "Remap = commit to that inventory before G0/compile."
            ),
            evidence={"code_roots": code_roots, "phase": "post_install_pre_compile"},
            operator_confirmation_required=True,
            resolution_options=["remap", "waive", "defer_blocks_adoption"],
        )
    )

    findings.append(
        _finding(
            id="baseline.human_material_before_compile",
            category="baseline",
            severity="warning",
            summary=(
                "Brownfield compile requires sufficient human product material for the "
                "requested scope; do not derive product rules from existing code. "
                "Remap = produce/register docs before `/compile-project`."
            ),
            evidence={
                "code_roots": code_roots,
                "product_doc_roots": product_docs,
                "phase": "post_install_pre_compile",
            },
            operator_confirmation_required=True,
            resolution_options=["remap", "defer_blocks_adoption"],
        )
    )

    if product_docs:
        findings.append(
            _finding(
                id="baseline.product_docs_candidate_present",
                category="baseline",
                severity="info",
                summary=(
                    "Structured product-doc tree found; confirm it is complete enough for "
                    "Definition of Ready and registered in source-registry after install."
                ),
                evidence={"paths": product_docs},
                operator_confirmation_required=True,
            )
        )
    else:
        findings.append(
            _finding(
                id="baseline.product_material_gap",
                category="baseline",
                severity="warning",
                summary=(
                    "Existing code without a detected `docs/product/` (or equivalent) tree. "
                    "Authoritative human material must be written and registered before a "
                    "coherent first compile; otherwise expect G0 blocking ambiguity."
                ),
                evidence={
                    "code_roots": code_roots,
                    "checked_product_doc_roots": list(_PRODUCT_DOC_CANDIDATES),
                },
                operator_confirmation_required=True,
                resolution_options=["remap", "waive", "defer_blocks_adoption"],
            )
        )

    return findings


def _ensure_category_coverage(findings: list[Finding]) -> list[Finding]:
    present = {f.category for f in findings}
    extras: list[Finding] = []
    for category in CATEGORIES:
        if category in present:
            continue
        if category == "remodel":
            extras.append(
                _finding(
                    id="remodel.none_open_yet",
                    category="remodel",
                    severity="info",
                    summary=(
                        "No remodel backlog items yet; unresolved findings in other categories "
                        "become the remodel backlog when the verdict is computed."
                    ),
                    evidence={"auto": True},
                    resolution_options=["remap"],
                )
            )
        else:
            extras.append(
                _finding(
                    id=f"{category}.none_detected",
                    category=category,
                    severity="info",
                    summary=f"No automatic findings in category `{category}`.",
                    evidence={"auto": True},
                )
            )
    return findings + extras


def _remodel_backlog_findings(findings: list[Finding]) -> list[Finding]:
    """Surface open items as remodel pointers (info) so verdict stays on source findings."""
    remodel: list[Finding] = []
    for finding in findings:
        if finding.category == "remodel":
            continue
        if finding.severity not in {"blocking", "warning"}:
            continue
        if finding.severity == "blocking" and blocking_is_resolved(finding):
            continue
        if finding.severity == "warning" and finding.resolution_status in RESOLVED_BLOCKING:
            continue
        if finding.resolution_status not in {"unresolved", "defer_blocks_adoption"}:
            continue
        remodel.append(
            _finding(
                id=f"remodel.from.{finding.id}",
                category="remodel",
                severity="info",
                summary=f"Backlog pointer - resolve `{finding.id}` ({finding.severity}).",
                evidence={
                    "source_finding_id": finding.id,
                    "source_severity": finding.severity,
                    "source_status": finding.resolution_status,
                },
                resolution_options=list(finding.resolution_options),
                operator_confirmation_required=finding.operator_confirmation_required,
            )
        )
    return remodel


def run_assessment(
    target: Path,
    *,
    source_root: Path | None = None,
    resolutions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = target.expanduser().resolve()
    findings = (
        _scan_engagement(target)
        + _scan_authority(target)
        + _scan_artifacts(target)
        + _scan_prerequisites(target, source_root=source_root)
        + _scan_baseline(target)
    )
    findings = apply_resolutions(findings, resolutions)
    findings = findings + _remodel_backlog_findings(findings)
    findings = _ensure_category_coverage(findings)

    # Verdict ignores informational remodel pointers (severity info).
    verdict = compute_verdict(findings)
    by_category: dict[str, Any] = {}
    for category in CATEGORIES:
        cat_findings = [f for f in findings if f.category == category]
        by_category[category] = {
            "empty": len(cat_findings) == 0,
            "findings": [f.to_dict() for f in cat_findings],
        }

    backlog = [
        f.to_dict()
        for f in findings
        if (
            (f.severity == "blocking" and not blocking_is_resolved(f))
            or (
                f.severity == "warning"
                and f.resolution_status in {"unresolved", "defer_blocks_adoption"}
            )
        )
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "target": str(target),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "categories": by_category,
        "findings": [f.to_dict() for f in findings],
        "backlog": backlog,
        "resolution_options_allowed": list(DEFAULT_RESOLUTION_OPTIONS),
        "notes": {
            "hybrid_mode_supported": False,
            "not_preflight": True,
            "not_diagnose": True,
            "not_gate_g0": True,
            "exclusive_governance": True,
            "legacy_fingerprints_checked": sorted(LEGACY_FRAMEWORK_FINGERPRINTS),
        },
    }


def format_human_report(report: dict[str, Any]) -> str:
    lines = [
        "Governed AI Team - adoption assessment",
        "=" * 40,
        f"Target:  {report['target']}",
        f"Verdict: {report['verdict']}",
        f"Generated (UTC): {report['generated_at']}",
        "",
        "This is NOT preflight, diagnose, or gate G0.",
        "Hybrid governance is not a supported option.",
        "",
    ]
    for category in CATEGORIES:
        section = report["categories"][category]
        lines.append(f"## {category}")
        if section["empty"]:
            lines.append("  (none)")
        for item in section["findings"]:
            lines.append(
                f"  [{item['severity']}] {item['id']} "
                f"({item['resolution_status']}): {item['summary']}"
            )
        lines.append("")
    if report["backlog"]:
        lines.append("## backlog")
        for item in report["backlog"]:
            lines.append(f"  - {item['id']} [{item['severity']}] {item['resolution_status']}")
        lines.append("")
    lines.append("Resolution options: " + ", ".join(report["resolution_options_allowed"]))
    lines.append(
        "Use --resolutions FILE to apply eliminate|remap|waive(+auth)|defer_blocks_adoption."
    )
    return "\n".join(lines) + "\n"


def load_resolutions_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("resolutions file must contain a JSON object")
    return data


def load_assessment_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("assessment report must be a JSON object")
    if data.get("kind") != REPORT_KIND:
        raise ValueError(f"assessment report kind must be {REPORT_KIND!r}")
    if data.get("verdict") not in VERDICTS:
        raise ValueError("assessment report missing valid verdict")
    return data


def assessment_gate_error(
    *,
    assessment_report: str | None,
    skip_assessment_gate: bool,
) -> str | None:
    """Return an error message when fresh install must not proceed."""
    if skip_assessment_gate or os.environ.get(ASSESSMENT_SKIP_ENV) == "1":
        return None
    if not assessment_report:
        return (
            "Fresh install aborted: provide --assessment-report PATH from "
            "`tools/assess.py` (verdict go|go_with_backlog), or pass "
            "--skip-assessment-gate to acknowledge exclusive-governance risk "
            f"(automation may set {ASSESSMENT_SKIP_ENV}=1)."
        )
    path = Path(assessment_report).expanduser().resolve()
    if not path.is_file():
        return f"Fresh install aborted: assessment report not found: {path}"
    try:
        report = load_assessment_report(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return f"Fresh install aborted: invalid assessment report: {exc}"
    if report["verdict"] == "no_go":
        return (
            "Fresh install aborted: assessment verdict is no_go. "
            "Resolve blocking findings or defer adoption; do not install in hybrid mode."
        )
    if report["verdict"] not in {"go", "go_with_backlog"}:
        return f"Fresh install aborted: unsupported assessment verdict {report['verdict']!r}"
    return None


def exit_code_for_verdict(verdict: str) -> int:
    if verdict in {"go", "go_with_backlog"}:
        return 0
    if verdict == "no_go":
        return 2
    return 1


__all__ = [
    "ASSESSMENT_SKIP_ENV",
    "CATEGORIES",
    "DEFAULT_RESOLUTION_OPTIONS",
    "Finding",
    "REPORT_KIND",
    "assessment_gate_error",
    "apply_resolutions",
    "blocking_is_resolved",
    "compute_verdict",
    "exit_code_for_verdict",
    "format_human_report",
    "load_assessment_report",
    "load_resolutions_file",
    "run_assessment",
]
