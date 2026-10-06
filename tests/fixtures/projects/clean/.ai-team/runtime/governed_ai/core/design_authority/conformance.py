"""Visual Conformance Runner — independent verification against Design Contracts.

Core owns captures (via privileged ``CaptureBackend``), reference loading, and
pixel comparison. Caller-supplied DOM/styles/text/screenshots/diff ratios are
never treated as verification truth.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from governed_ai.core.design_authority.capture_backend import (
    CaptureBackend,
    CaptureObservation,
    resolve_capture_backend,
    strip_forbidden_truth,
)
from governed_ai.core.design_authority.contract import load_design_contract, unwrap
from governed_ai.core.design_authority.divergences import (
    classify_divergence,
    report_blocks_progress,
)
from governed_ai.core.design_authority.hashing import sha256_bytes, sha256_canonical
from governed_ai.core.design_authority.models import SCHEMA_VERSION
from governed_ai.core.design_authority.paths import (
    conformance_path,
    ensure_design_layout,
    evidence_dir,
)
from governed_ai.core.design_authority.pixel_compare import compare_png_pixels
from governed_ai.core.design_authority.registry import load_artifact
from governed_ai.core.ensemble_composition import (
    assert_composition_live,
    ensure_frozen_composition_checkouts,
    require_current_composition,
    requires_product_composition,
    ui_member_id,
)
from governed_ai.core.persistence.io import dump_yaml
from governed_ai.core.workspace import Workspace

CaptureFn = Callable[[dict[str, Any]], Any]

_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

IMAGE_SOURCE_TYPES: frozenset[str] = frozenset(
    {"png", "jpg", "jpeg", "webp", "screenshot", "wireframe"}
)

# Contract fields that may require styles/DOM evidence when authoritative.
STYLE_CONTRACT_FIELDS: tuple[str, ...] = (
    "tokens",
    "typography",
    "colors",
    "spacing",
    "radii",
    "shadows",
    "icons",
    "accessibility",
    "motion",
    "structure",
    "navigation",
    "behaviors",
    "responsive_rules",
    "breakpoints",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConformanceError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _run_git(workspace_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"safe.directory={workspace_root}",
            *args,
        ],
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def validate_commit_sha(workspace: Workspace, commit_sha: str) -> str:
    """Validate format, object existence, and worktree HEAD match."""
    sha = str(commit_sha or "").strip().lower()
    if not _GIT_SHA_RE.fullmatch(sha):
        raise ConformanceError(
            "invalid_commit_sha",
            "commit_sha must be a git SHA (40 hex) or abbreviation (≥7 hex)",
            details={"commit_sha": commit_sha},
        )
    resolved = _run_git(workspace.root, ["rev-parse", "--verify", f"{sha}^{{commit}}"])
    if resolved.returncode != 0:
        # Fallback: cat-file -t
        typed = _run_git(workspace.root, ["cat-file", "-t", sha])
        if typed.returncode != 0 or typed.stdout.strip() != "commit":
            raise ConformanceError(
                "unknown_commit_sha",
                "commit_sha is not a known commit in this repository",
                details={"commit_sha": sha, "stderr": (resolved.stderr or typed.stderr).strip()},
            )
        full = _run_git(workspace.root, ["rev-parse", sha]).stdout.strip().lower()
    else:
        full = resolved.stdout.strip().lower()

    head = _run_git(workspace.root, ["rev-parse", "HEAD"])
    if head.returncode != 0:
        raise ConformanceError(
            "git_head_unavailable",
            "unable to resolve worktree HEAD for conformance verification",
            details={"stderr": head.stderr.strip()},
        )
    head_sha = head.stdout.strip().lower()
    if not (head_sha.startswith(sha) or sha.startswith(head_sha) or head_sha == full):
        raise ConformanceError(
            "commit_sha_worktree_mismatch",
            "commit_sha does not match the worktree HEAD used for verification",
            details={"commit_sha": full or sha, "head": head_sha},
        )
    return full or head_sha


def _prepare_isolated_checkout(workspace: Workspace, commit_sha: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="governed-design-verify-"))
    completed = _run_git(
        workspace.root,
        ["worktree", "add", "--detach", str(root), commit_sha],
    )
    if completed.returncode != 0:
        raise ConformanceError(
            "isolated_checkout_failed",
            "unable to prepare isolated checkout for visual verification",
            details={"stderr": completed.stderr.strip()},
        )
    head = _run_git(root, ["rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip().lower() != commit_sha.lower():
        _run_git(workspace.root, ["worktree", "remove", "--force", str(root)])
        raise ConformanceError(
            "isolated_checkout_mismatch",
            "isolated verification checkout does not match commit_sha",
        )
    return root


def _release_isolated_checkout(workspace: Workspace, root: Path | None) -> None:
    if root is None:
        return
    _run_git(workspace.root, ["worktree", "remove", "--force", str(root)])


def _viewport_name(viewport: Any) -> str:
    if isinstance(viewport, dict):
        return str(viewport.get("name") or viewport.get("id") or "")
    return str(viewport or "")


def _normalize_viewport(viewport: Any) -> dict[str, Any]:
    if isinstance(viewport, dict):
        return dict(viewport)
    return {"name": str(viewport or "")}


def _target_tuple(target: dict[str, Any] | None) -> tuple[str, str, str, str]:
    t = target or {}
    return (
        str(t.get("screen") or t.get("page") or ""),
        str(t.get("route") or ""),
        str(t.get("state") or ""),
        str(t.get("viewport") or ""),
    )


def _media_kind(source_type: str) -> str:
    st = str(source_type or "").lower()
    if st in IMAGE_SOURCE_TYPES:
        return "image"
    if st in {"tokens_json", "tokens"}:
        return "tokens"
    if st in {"markdown_spec", "text_spec", "html_static"}:
        return "text_spec"
    if st in {"svg"}:
        return "vector"
    if st in {"pdf"}:
        return "document"
    return st or "other"


def _field_is_authoritative_requirement(field: Any) -> bool:
    """True when a provenance-tagged contract field carries authoritative content."""
    if field is None:
        return False
    if isinstance(field, dict) and "origin" in field and "value" in field:
        if not field.get("authoritative", False):
            return False
        value = field.get("value")
    else:
        value = field
    if value is None:
        return False
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return False
    return True


def _cartesian_combinations(
    routes: list[Any],
    states: list[Any],
    viewports: list[Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    route_list = [str(r) for r in routes] or [""]
    state_list = [str(s) for s in states] or [""]
    viewport_list = [_normalize_viewport(v) for v in viewports] or [{"name": ""}]
    combos: list[tuple[str, str, dict[str, Any]]] = []
    for route in route_list:
        for state in state_list:
            for viewport in viewport_list:
                combos.append((route, state, viewport))
    return combos


def _score_target_match(
    *,
    route: str,
    state: str,
    viewport_name: str,
    target: dict[str, Any],
) -> int | None:
    """Return match score (higher better) or None if contradictory / no match."""
    t_route = str(target.get("route") or "")
    t_state = str(target.get("state") or "")
    t_viewport = str(target.get("viewport") or "")
    if t_route and t_route != route:
        return None
    if t_state and t_state != state:
        return None
    if t_viewport and t_viewport != viewport_name:
        return None
    score = 0
    if t_route and t_route == route:
        score += 4
    if t_state and t_state == state:
        score += 2
    if t_viewport and t_viewport == viewport_name:
        score += 1
    # Empty target matches everything with score 0 (fallback).
    return score


def _load_reference_png(
    workspace: Workspace, design_artifact_id: str
) -> tuple[bytes, dict[str, Any]]:
    artifact = load_artifact(workspace, design_artifact_id)
    source_path = artifact.get("source_path")
    if not source_path:
        raise ConformanceError(
            "reference_not_local",
            f"authoritative artifact {design_artifact_id!r} has no local source_path",
            details={"design_artifact_id": design_artifact_id},
        )
    path = (workspace.root / str(source_path)).resolve()
    try:
        path.relative_to(workspace.root.resolve())
    except ValueError as exc:
        raise ConformanceError(
            "forbidden_path_traversal",
            "reference path escapes workspace root",
            details={"source_path": source_path},
        ) from exc
    if not path.is_file():
        raise ConformanceError(
            "reference_missing",
            f"reference file missing for {design_artifact_id!r}",
            details={"source_path": source_path},
        )
    return path.read_bytes(), artifact


def _stage_or_write_bytes(
    *,
    dest: Path,
    data: bytes,
    persist: bool,
    staged_binaries: list[dict[str, Any]],
    workspace: Workspace,
) -> Path:
    if persist:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest
    tmp = tempfile.NamedTemporaryFile(prefix="vcr-", suffix=dest.suffix or ".bin", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
    finally:
        tmp.close()
    try:
        dest_relative = dest.relative_to(workspace.root).as_posix()
    except ValueError:
        dest_relative = dest.as_posix()
    staged_binaries.append({"dest_relative": dest_relative, "temp_path": str(tmp_path)})
    return dest


def _write_capture_evidence(
    directory: Path,
    *,
    label: str,
    route: str,
    state: str,
    viewport: dict[str, Any],
    observation: CaptureObservation,
    commit_sha: str,
    reference_id: str | None,
    persist: bool,
    staged_binaries: list[dict[str, Any]],
    workspace: Workspace,
    planned_writes: list[dict[str, Any]],
) -> dict[str, Any]:
    meta = {
        "label": label,
        "route": route,
        "state": state,
        "viewport": viewport,
        "commit_sha": commit_sha,
        "reference_id": reference_id,
        "captured_at": _now_iso(),
    }
    screenshot_hash = None
    screenshot_path: str | None = None
    if isinstance(observation.screenshot_bytes, (bytes, bytearray)):
        png_dest = directory / f"{label}.png"
        written = _stage_or_write_bytes(
            dest=png_dest,
            data=bytes(observation.screenshot_bytes),
            persist=persist,
            staged_binaries=staged_binaries,
            workspace=workspace,
        )
        screenshot_hash = sha256_bytes(bytes(observation.screenshot_bytes))
        screenshot_path = written.as_posix()

    dom_doc = {
        "dom": observation.dom or {},
        "styles": observation.styles or {},
        "text": observation.text or [],
        "components": observation.components or [],
    }
    dom_path = directory / f"{label}.dom.json"
    dom_text = json.dumps(dom_doc, indent=2, ensure_ascii=False)
    if persist:
        directory.mkdir(parents=True, exist_ok=True)
        dom_path.write_text(dom_text, encoding="utf-8")
        meta_path = directory / f"{label}.meta.yaml"
        dump_yaml(meta_path, meta)
    else:
        planned_writes.append({"path": str(dom_path.as_posix()), "document": dom_doc})
        planned_writes.append(
            {"path": str((directory / f"{label}.meta.yaml").as_posix()), "document": meta}
        )
        meta_path = directory / f"{label}.meta.yaml"

    return {
        "label": label,
        "route": route,
        "state": state,
        "viewport": viewport,
        "commit_sha": commit_sha,
        "reference_id": reference_id,
        "screenshot_path": screenshot_path,
        "screenshot_hash": screenshot_hash,
        "dom_snapshot_path": dom_path.as_posix(),
        "dom_snapshot_hash": sha256_bytes(dom_text.encode("utf-8")),
        "meta_path": meta_path.as_posix(),
        "environment": observation.environment or {},
    }


def _match_image_references(
    *,
    route: str,
    state: str,
    viewport_name: str,
    refs: list[dict[str, Any]],
    workspace: Workspace,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (best_matches, ambiguity_issues) for image-kind authoritative refs."""
    scored: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    issues: list[dict[str, Any]] = []
    for ref in refs:
        aid = str(ref.get("design_artifact_id") or "")
        if not aid:
            continue
        try:
            artifact = load_artifact(workspace, aid)
        except Exception:
            continue
        source_type = str(artifact.get("source_type") or ref.get("source_type") or "")
        if _media_kind(source_type) != "image":
            continue
        target = ref.get("target") if isinstance(ref.get("target"), dict) else {}
        score = _score_target_match(
            route=route, state=state, viewport_name=viewport_name, target=target
        )
        if score is None:
            continue
        scored.append((score, ref, artifact))

    if not scored:
        return [], issues

    best_score = max(s for s, _, _ in scored)
    best = [(ref, art) for s, ref, art in scored if s == best_score]

    # Contradictory: multiple authoritative image mockups for same media+target.
    if len(best) > 1:
        # Group by exact target key among best.
        by_target: dict[tuple[str, str, str, str], list[str]] = {}
        for ref, art in best:
            key = _target_tuple(ref.get("target") if isinstance(ref.get("target"), dict) else {})
            by_target.setdefault(key, []).append(str(art.get("design_artifact_id") or ref.get("design_artifact_id")))
        for key, ids in by_target.items():
            unique = sorted(set(ids))
            if len(unique) > 1:
                issues.append(
                    {
                        "code": "ambiguous_contradictory_mockups",
                        "target": {
                            "screen": key[0],
                            "route": key[1],
                            "state": key[2],
                            "viewport": key[3],
                        },
                        "design_artifact_ids": unique,
                    }
                )
        # Still return all best for caller to refuse compare.
        return [{"ref": r, "artifact": a} for r, a in best], issues

    return [{"ref": best[0][0], "artifact": best[0][1]}], issues


def _check_style_fields(
    contract: dict[str, Any],
    observation: CaptureObservation,
    *,
    authority: str,
    capture_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    divergences: list[dict[str, Any]] = []
    has_styles = bool(observation.styles)
    has_dom = bool(observation.dom)
    for field_name in STYLE_CONTRACT_FIELDS:
        field = contract.get(field_name)
        if not _field_is_authoritative_requirement(field):
            continue
        value = unwrap(field)
        # Heuristic checks when capture provides styles/DOM.
        if field_name in {"tokens", "typography", "colors", "spacing", "radii", "shadows"}:
            if not has_styles:
                checks.append(
                    {
                        "type": field_name,
                        "status": "unverifiable",
                        "reason": "capture_missing_styles",
                        "capture": capture_label,
                    }
                )
                continue
            # Presence-level check: required token keys if value is a mapping.
            if isinstance(value, dict) and value:
                missing = [k for k in value if k not in observation.styles]
                if missing:
                    divergences.append(
                        classify_divergence(
                            kind="defect",
                            severity="blocking",
                            authority_level=authority,
                            explanation=f"authoritative {field_name} keys missing from captured styles",
                            details={"capture": capture_label, "missing": missing},
                        )
                    )
                else:
                    checks.append({"type": field_name, "status": "passed", "capture": capture_label})
            else:
                checks.append(
                    {
                        "type": field_name,
                        "status": "unverifiable",
                        "reason": "no_automatable_assertion",
                        "capture": capture_label,
                    }
                )
        elif field_name in {"structure", "navigation", "behaviors", "responsive_rules", "breakpoints"}:
            if not has_dom and not has_styles:
                checks.append(
                    {
                        "type": field_name,
                        "status": "unverifiable",
                        "reason": "capture_missing_dom_or_styles",
                        "capture": capture_label,
                    }
                )
            else:
                checks.append(
                    {
                        "type": field_name,
                        "status": "unverifiable",
                        "reason": "no_automatable_assertion",
                        "capture": capture_label,
                    }
                )
        elif field_name in {"icons", "accessibility", "motion"}:
            checks.append(
                {
                    "type": field_name,
                    "status": "unverifiable",
                    "reason": "no_automatable_assertion",
                    "capture": capture_label,
                }
            )
    return checks, divergences


def run_visual_conformance(
    workspace: Workspace,
    *,
    report_id: str,
    design_contract_id: str,
    work_unit_id: str,
    commit_sha: str,
    verifier_role: str,
    implementer_role: str | None = None,
    lease_id: str | None = None,
    epoch: int | None = None,
    expected_lease_id: str | None = None,
    expected_epoch: int | None = None,
    observations: list[dict[str, Any]] | None = None,
    capture_backend: CaptureBackend | None = None,
    capture_fn: CaptureFn | CaptureBackend | None = None,
    agent_claimed_passed: bool | None = None,
    verification_profile: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run conformance checks and produce a Core-owned report.

    Returns a result dict::

        {
          "report": {...},
          "planned_writes": [{"path": ..., "document": ...}],
          "staged_binaries": [{"dest_relative": ..., "temp_path": ...}],
        }

    When ``persist=True``, YAML/binaries are written immediately and
    ``planned_writes`` / ``staged_binaries`` are empty. When ``persist=False``,
    nothing is written under governed design paths; the handler must commit
    via transaction (YAML) and optionally promote staged binaries.
    """
    if implementer_role and verifier_role == implementer_role:
        raise ConformanceError(
            "same_actor_implementation_and_verification",
            "frontend-developer cannot be the sole visual verifier of their own work",
            details={"role": verifier_role},
        )
    if expected_lease_id is not None and lease_id != expected_lease_id:
        raise ConformanceError(
            "stale_lease",
            "visual result lease_id does not match current lease",
            details={"expected": expected_lease_id, "actual": lease_id},
        )
    if expected_epoch is not None and epoch != expected_epoch:
        raise ConformanceError(
            "stale_epoch",
            "visual result epoch does not match current epoch",
            details={"expected": expected_epoch, "actual": epoch},
        )

    frozen_roots: dict[str, Path] = {}
    if requires_product_composition(workspace):
        try:
            composition = require_current_composition(workspace)
            assert_composition_live(workspace, composition)
            frozen_roots = ensure_frozen_composition_checkouts(workspace, composition)
        except Exception as exc:
            from governed_ai.core.commands.errors import GatewayError

            if isinstance(exc, GatewayError):
                raise ConformanceError(
                    "composition_not_current",
                    exc.message,
                    details={"path": exc.path},
                ) from exc
            raise
        ui_id = ui_member_id(workspace)
        pins = composition.get("members") or {}
        ui_pin = str(pins.get(ui_id) or "")
        sha = str(commit_sha or "").strip().lower()
        if sha.startswith("cr-"):
            if sha != str(composition.get("id") or "").lower():
                raise ConformanceError(
                    "composition_id_mismatch",
                    "commit_sha composition id does not match the current pin",
                    details={"commit_sha": commit_sha, "current": composition.get("id")},
                )
            verified_sha = ui_pin
        else:
            if ui_pin and sha and not (ui_pin.startswith(sha) or sha.startswith(ui_pin)):
                raise ConformanceError(
                    "commit_sha_composition_mismatch",
                    "frontend SHA does not match the pinned composition",
                    details={"commit_sha": commit_sha, "pinned": ui_pin, "member_id": ui_id},
                )
            verified_sha = ui_pin or sha
    else:
        verified_sha = validate_commit_sha(workspace, commit_sha)

    # Reject implementer-supplied truth channels (strip; never use as evidence).
    sanitized_observations = [strip_forbidden_truth(o) for o in (observations or []) if isinstance(o, dict)]
    for raw in observations or []:
        if isinstance(raw, dict) and any(k in raw for k in (
            "observed_dom",
            "observed_styles",
            "observed_text",
            "observed_components",
            "screenshot_bytes",
            "reference_screenshot_bytes",
            "diff_ratio",
            "allowed_by_tolerance_rule",
            "environment_variance",
        )):
            # Explicit rejection: caller tried to inject truth.
            raise ConformanceError(
                "forbidden_caller_truth",
                "caller must not supply observation truth "
                "(DOM/styles/text/components/screenshots/diff_ratio/tolerances); "
                "use a privileged CaptureBackend",
                details={"rejected_keys": sorted(
                    k for k in raw if k in {
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
                )},
            )

    contract = load_design_contract(workspace, design_contract_id)
    tolerances_field = contract.get("tolerances")
    tolerances = unwrap(tolerances_field) or {}
    if not isinstance(tolerances, dict):
        tolerances = {}
    level = str(contract.get("conformance_level") or tolerances.get("level") or "tolerant_visual")
    mandatory_text = list(unwrap(contract.get("mandatory_text")) or [])
    mandatory_elements = list(unwrap(contract.get("mandatory_elements")) or [])
    forbidden_elements = list(unwrap(contract.get("forbidden_elements")) or [])
    required_states = list(unwrap(contract.get("states")) or [])
    required_viewports = list(unwrap(contract.get("viewports")) or [])
    routes = list(unwrap(contract.get("routes")) or [])
    design_mode = str(contract.get("design_mode") or "")

    auth_refs = [
        r for r in (contract.get("references") or []) if r.get("authority_level") == "authoritative"
    ]
    advisory_refs = [
        r for r in (contract.get("references") or []) if r.get("authority_level") == "advisory"
    ]
    authority = "authoritative" if auth_refs else "advisory"

    ensure_design_layout(workspace)
    evidence_root = evidence_dir(workspace, report_id)
    backend = resolve_capture_backend(capture_backend, capture_fn)
    isolated_root: Path | None = None
    application_started = False

    divergences: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    planned_writes: list[dict[str, Any]] = []
    staged_binaries: list[dict[str, Any]] = []
    incomplete_evidence = False

    combinations = _cartesian_combinations(routes, required_states, required_viewports)

    if backend is None:
        incomplete_evidence = True
        for route, state, viewport in combinations:
            divergences.append(
                classify_divergence(
                    kind="defect",
                    severity="blocking" if design_mode in {"conform", "adapt"} else "advisory",
                    authority_level=authority,
                    explanation=(
                        "no privileged CaptureBackend available; "
                        "visual conformance is unverifiable"
                    ),
                    details={
                        "route": route,
                        "state": state,
                        "viewport": _viewport_name(viewport),
                    },
                )
            )
            checks.append(
                {
                    "type": "capture",
                    "status": "unverifiable",
                    "route": route,
                    "state": state,
                    "viewport": _viewport_name(viewport),
                }
            )
    else:
        try:
            if frozen_roots:
                isolated_root = frozen_roots[ui_member_id(workspace)]
            else:
                isolated_root = _prepare_isolated_checkout(workspace, verified_sha)
            backend.configure_workspace(isolated_root, verified_sha)
            configure_members = getattr(backend, "configure_member_workspaces", None)
            if callable(configure_members) and frozen_roots:
                configure_members(frozen_roots, verified_sha)
            profile = verification_profile or {}
            launch = profile.get("start_command")
            if launch is not None:
                if not isinstance(launch, list) or not all(
                    isinstance(item, str) and item for item in launch
                ):
                    raise ConformanceError(
                        "invalid_start_command",
                        "verification start_command must be a non-empty argv list",
                    )
                allowed = profile.get("allowed_start_commands") or []
                if launch not in allowed:
                    raise ConformanceError(
                        "start_command_not_allowed",
                        "application start command is not explicitly allowed by profile",
                    )
                backend.start_application(list(launch))
                application_started = True
                readiness = profile.get("readiness")
                if not isinstance(readiness, dict) or not readiness:
                    raise ConformanceError(
                        "missing_readiness_condition",
                        "a deterministic readiness condition is required",
                    )
                backend.wait_ready(readiness)
            backend.ensure_ready()
        except ConformanceError:
            if application_started:
                backend.stop_application()
            if not frozen_roots:
                _release_isolated_checkout(workspace, isolated_root)
            raise
        except Exception as exc:  # noqa: BLE001 — surface as unverifiable capture failure
            incomplete_evidence = True
            divergences.append(
                classify_divergence(
                    kind="defect",
                    severity="blocking",
                    authority_level=authority,
                    explanation=f"capture backend not ready: {exc}",
                    details={"error": str(exc)},
                )
            )
            backend = None

    if backend is not None:
        threshold_raw = tolerances.get("difference_threshold")
        threshold = 0.02 if threshold_raw is None else float(threshold_raw)
        allow_resize = bool(tolerances.get("allow_resize") or tolerances.get("resize_on_dimension_mismatch"))
        masked_regions = list(tolerances.get("masked_regions") or [])
        free_zones = list(unwrap(contract.get("free_zones")) or [])

        for index, (route, state, viewport) in enumerate(combinations):
            vname = _viewport_name(viewport)
            label = f"capture-{index:02d}"
            try:
                backend.open_route(route)
                backend.prepare_state(state)
                backend.set_viewport(viewport)
                observation = backend.capture()
                if not isinstance(observation, CaptureObservation):
                    from governed_ai.core.design_authority.capture_backend import (
                        observation_from_mapping,
                    )

                    observation = observation_from_mapping(observation)
            except Exception as exc:  # noqa: BLE001
                incomplete_evidence = True
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level=authority,
                        explanation=f"capture failed for route={route!r} state={state!r} viewport={vname!r}",
                        details={"error": str(exc)},
                    )
                )
                checks.append(
                    {
                        "type": "capture",
                        "status": "failed",
                        "route": route,
                        "state": state,
                        "viewport": vname,
                    }
                )
                continue

            matches, ambiguity = _match_image_references(
                route=route,
                state=state,
                viewport_name=vname,
                refs=auth_refs or advisory_refs,
                workspace=workspace,
            )
            for issue in ambiguity:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level="authoritative",
                        explanation="ambiguous contradictory authoritative mockups for the same target",
                        details=issue,
                    )
                )

            reference_id = None
            if matches and not ambiguity:
                reference_id = str(
                    matches[0]["artifact"].get("design_artifact_id")
                    or matches[0]["ref"].get("design_artifact_id")
                )
            elif auth_refs and not matches:
                # No image reference for this combo — coverage of image compare is N/A;
                # still record capture. Missing required image ref only blocks when
                # design mode requires authoritative visual match and refs exist elsewhere.
                pass

            evidence = _write_capture_evidence(
                evidence_root / label,
                label=label,
                route=route,
                state=state,
                viewport=viewport,
                observation=observation,
                commit_sha=verified_sha,
                reference_id=reference_id,
                persist=persist,
                staged_binaries=staged_binaries,
                workspace=workspace,
                planned_writes=planned_writes,
            )
            captures.append(evidence)

            # Text / component checks from privileged capture only.
            observed_text = list(observation.text or [])
            observed_components = list(observation.components or [])

            for text in mandatory_text:
                if text not in observed_text:
                    divergences.append(
                        classify_divergence(
                            kind="defect",
                            severity="blocking",
                            authority_level=authority,
                            explanation=f"mandatory text missing: {text!r}",
                            details={"capture": label},
                        )
                    )
                else:
                    checks.append({"type": "textual", "status": "passed", "text": text})

            for element in mandatory_elements:
                if element not in observed_components:
                    divergences.append(
                        classify_divergence(
                            kind="defect",
                            severity="blocking",
                            authority_level=authority,
                            explanation=f"mandatory element missing: {element!r}",
                            details={"capture": label},
                        )
                    )
                else:
                    checks.append(
                        {"type": "component_presence", "status": "passed", "element": element}
                    )

            for element in forbidden_elements:
                if element in observed_components:
                    divergences.append(
                        classify_divergence(
                            kind="defect",
                            severity="blocking",
                            authority_level=authority,
                            explanation=f"forbidden element present: {element!r}",
                            details={"capture": label},
                        )
                    )

            style_checks, style_divs = _check_style_fields(
                contract, observation, authority=authority, capture_label=label
            )
            checks.extend(style_checks)
            divergences.extend(style_divs)

            # Pixel compare against Core-loaded reference (never from caller).
            if ambiguity:
                checks.append(
                    {
                        "type": "image_comparison",
                        "status": "failed",
                        "reason": "ambiguous_contradictory_mockups",
                        "capture": label,
                    }
                )
            elif reference_id and observation.screenshot_bytes:
                try:
                    ref_bytes, _artifact = _load_reference_png(workspace, reference_id)
                except ConformanceError as exc:
                    divergences.append(
                        classify_divergence(
                            kind="defect",
                            severity="blocking",
                            authority_level=authority,
                            explanation=exc.message,
                            details=exc.details,
                        )
                    )
                    checks.append(
                        {
                            "type": "image_comparison",
                            "status": "failed",
                            "reason": exc.code,
                            "capture": label,
                        }
                    )
                else:
                    reference_dest = evidence_root / label / f"{label}.reference.png"
                    _stage_or_write_bytes(
                        dest=reference_dest,
                        data=ref_bytes,
                        persist=persist,
                        staged_binaries=staged_binaries,
                        workspace=workspace,
                    )
                    compare = compare_png_pixels(
                        reference_png=ref_bytes,
                        observed_png=bytes(observation.screenshot_bytes),
                        masked_regions=masked_regions,
                        allow_resize=allow_resize,
                        difference_threshold=threshold,
                    )
                    if compare.diff_image_bytes:
                        diff_dest = evidence_root / label / f"{label}.diff.png"
                        _stage_or_write_bytes(
                            dest=diff_dest,
                            data=compare.diff_image_bytes,
                            persist=persist,
                            staged_binaries=staged_binaries,
                            workspace=workspace,
                        )
                    evidence.update(
                        {
                            "reference_screenshot_path": reference_dest.as_posix(),
                            "reference_screenshot_hash": compare.reference_hash,
                            "observed_screenshot_hash": compare.observed_hash,
                            "diff_image_path": (
                                diff_dest.as_posix() if compare.diff_image_bytes else None
                            ),
                            "diff_image_hash": (
                                sha256_bytes(compare.diff_image_bytes)
                                if compare.diff_image_bytes
                                else None
                            ),
                            "reference_dimensions": list(compare.reference_dimensions),
                            "observed_dimensions": list(compare.observed_dimensions),
                            "diff_ratio": compare.diff_ratio,
                            "masked_regions": compare.masked_regions_applied,
                        }
                    )
                    if compare.blocking_reason == "dimension_mismatch":
                        divergences.append(
                            classify_divergence(
                                kind="defect",
                                severity="blocking",
                                authority_level=authority,
                                explanation="screenshot dimensions differ from reference",
                                details={
                                    "capture": label,
                                    "reference_dimensions": list(compare.reference_dimensions),
                                    "observed_dimensions": list(compare.observed_dimensions),
                                },
                            )
                        )
                        checks.append(
                            {
                                "type": "image_comparison",
                                "status": "failed",
                                "reason": "dimension_mismatch",
                                "capture": label,
                            }
                        )
                    elif compare.diff_ratio <= threshold:
                        checks.append(
                            {
                                "type": "image_comparison",
                                "status": "passed",
                                "diff_ratio": compare.diff_ratio,
                                "threshold": threshold,
                                "masked_regions": compare.masked_regions_applied,
                                "reference_hash": compare.reference_hash,
                                "observed_hash": compare.observed_hash,
                                "resized": compare.resized,
                                "capture": label,
                            }
                        )
                    elif design_mode == "adapt" and free_zones:
                        # "adapt" mode explicitly permits deviation from the mockup
                        # within Design Contract-declared free zones — an above
                        # threshold diff is a governed adaptation, not a defect.
                        tolerance_rule = ",".join(
                            sorted(
                                str(zone.get("id") or zone)
                                if isinstance(zone, dict)
                                else str(zone)
                                for zone in free_zones
                            )
                        )
                        divergences.append(
                            classify_divergence(
                                kind="allowed_adaptation",
                                severity="advisory",
                                authority_level=authority,
                                explanation="visual difference exceeds tolerance but is within a declared adapt-mode free zone",
                                contract_tolerance_rule=tolerance_rule,
                                details={
                                    "diff_ratio": compare.diff_ratio,
                                    "threshold": threshold,
                                    "masked_regions": compare.masked_regions_applied,
                                    "reference_hash": compare.reference_hash,
                                    "observed_hash": compare.observed_hash,
                                    "capture": label,
                                },
                            )
                        )
                        checks.append(
                            {
                                "type": "image_comparison",
                                "status": "allowed_adaptation",
                                "diff_ratio": compare.diff_ratio,
                                "threshold": threshold,
                                "capture": label,
                            }
                        )
                    else:
                        # A named free-zone cannot excuse arbitrary pixels outside
                        # "adapt" mode. Only coordinate masks compiled into
                        # masked_regions affect the Core-owned ratio directly.
                        divergences.append(
                            classify_divergence(
                                kind="defect",
                                severity="blocking",
                                authority_level=authority,
                                explanation="visual difference exceeds contract tolerance",
                                details={
                                    "diff_ratio": compare.diff_ratio,
                                    "threshold": threshold,
                                    "masked_regions": compare.masked_regions_applied,
                                    "reference_hash": compare.reference_hash,
                                    "observed_hash": compare.observed_hash,
                                    "capture": label,
                                },
                            )
                        )
                        checks.append(
                            {
                                "type": "image_comparison",
                                "status": "failed",
                                "diff_ratio": compare.diff_ratio,
                                "threshold": threshold,
                                "capture": label,
                            }
                        )
            elif reference_id and not observation.screenshot_bytes:
                incomplete_evidence = True
                checks.append(
                    {
                        "type": "image_comparison",
                        "status": "unverifiable",
                        "reason": "capture_missing_screenshot",
                        "capture": label,
                    }
                )
            elif auth_refs and design_mode in {"conform", "adapt"} and not matches:
                # Required combo has no matching reference image — not necessarily a
                # coverage failure for image compare; textual checks still apply.
                checks.append(
                    {
                        "type": "image_comparison",
                        "status": "unverifiable",
                        "reason": "no_matching_reference_image",
                        "capture": label,
                        "route": route,
                        "state": state,
                        "viewport": vname,
                    }
                )

    # Coverage: every required route×state×viewport must have a capture when backend ran.
    if backend is not None:
        captured_keys = {
            (
                str(c.get("route") or ""),
                str(c.get("state") or ""),
                _viewport_name(c.get("viewport")),
            )
            for c in captures
        }
        for route, state, viewport in combinations:
            key = (route, state, _viewport_name(viewport))
            if key not in captured_keys and design_mode in {"conform", "adapt"}:
                divergences.append(
                    classify_divergence(
                        kind="defect",
                        severity="blocking",
                        authority_level=authority,
                        explanation=(
                            f"missing verification for route={route!r} "
                            f"state={state!r} viewport={_viewport_name(viewport)!r}"
                        ),
                        details={"route": route, "state": state, "viewport": _viewport_name(viewport)},
                    )
                )

    # Silence unused sanitized list (kept for future non-truth metadata).
    _ = sanitized_observations

    # "no_matching_reference_image" means the image check is not applicable to this
    # combo (no authoritative mockup targets it) — not missing/incomplete evidence.
    # Every other "unverifiable" reason reflects a real evidence gap (missing capture
    # data, or an authoritative requirement with no automatable assertion) and must
    # keep the report from silently passing.
    if any(
        item.get("status") == "unverifiable" and item.get("reason") != "no_matching_reference_image"
        for item in checks
    ):
        incomplete_evidence = True

    blocks = report_blocks_progress(divergences)
    if agent_claimed_passed and blocks:
        divergences.append(
            classify_divergence(
                kind="defect",
                severity="blocking",
                authority_level="authoritative" if auth_refs else "advisory",
                explanation="agent claimed passed but Core recomputed blocking divergences",
                details={"agent_claimed_passed": True},
            )
        )
        blocks = True

    # Advisory-only references: never auto-block solely from advisory authority.
    if not auth_refs and advisory_refs:
        for item in divergences:
            if item.get("authority_level") == "advisory":
                item["blocks_progress"] = False
        blocks = report_blocks_progress(divergences)

    if blocks:
        status = "failed"
    elif incomplete_evidence or (backend is None):
        status = "unverifiable"
    else:
        status = "passed"

    # Never pass without a backend / complete required evidence.
    if status == "passed" and (backend is None or incomplete_evidence):
        status = "unverifiable"

    report = {
        "report_id": report_id,
        "schema_version": SCHEMA_VERSION,
        "design_contract_id": design_contract_id,
        "design_contract_hash": contract.get("contract_hash"),
        "work_unit_id": work_unit_id,
        "commit_sha": verified_sha,
        "verifier_role": verifier_role,
        "implementer_role": implementer_role,
        "lease_id": lease_id,
        "epoch": epoch,
        "conformance_level": level,
        "tolerances": tolerances,
        "checks": checks,
        "captures": captures,
        "divergences": divergences,
        "blocks_progress": blocks,
        "status": status,
        "created_at": _now_iso(),
    }
    report["report_hash"] = sha256_canonical(
        {k: v for k, v in report.items() if k != "report_hash"}
    )

    report_path = conformance_path(workspace, report_id)
    if persist:
        dump_yaml(report_path, report)
        planned_writes = []
        staged_binaries = []
    else:
        planned_writes.insert(
            0,
            {"path": report_path.as_posix(), "document": report},
        )

    if application_started and backend is not None:
        backend.stop_application()
    if not frozen_roots:
        _release_isolated_checkout(workspace, isolated_root)

    return {
        "report": report,
        "planned_writes": planned_writes,
        "staged_binaries": staged_binaries,
    }
