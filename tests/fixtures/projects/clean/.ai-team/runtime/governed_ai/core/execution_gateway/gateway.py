"""Agent Execution Gateway — compile, dispatch, verify, promote or reject."""

from __future__ import annotations

import copy
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from governed_ai.core.execution_gateway.capabilities import assert_capabilities
from governed_ai.core.execution_gateway.check_registry import (
    assert_check_authorized,
    normalize_check_name,
    registry_blocking,
    resolve_required_checks,
)
from governed_ai.core.execution_gateway.context import (
    assert_context_hash,
    assert_package_hash_matches,
    compile_context_package,
    hash_context_package,
)
from governed_ai.core.execution_gateway.contracts import (
    MAX_ARTIFACT_BYTES,
    SCHEMA_VERSION,
    CapabilityDescriptor,
    ExecutionRequest,
    ExecutionResult,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.execution_gateway.evidence import (
    assert_blocking_check_trust,
    build_evidence_manifest,
    persist_evidence_manifest,
    verify_artifact,
)
from governed_ai.core.execution_gateway.legacy import LegacyExecutionResultAdapter
from governed_ai.core.execution_gateway.progress import ProgressEventType, make_progress_event
from governed_ai.core.execution_gateway.role_resolver import assert_role_procedure, resolve_role
from governed_ai.core.execution_gateway.scope import compute_effective_scope
from governed_ai.core.execution_gateway.security import (
    assert_command_allowed,
    assert_requested_commands_allowed,
)
from governed_ai.core.execution_gateway.transactional import (
    assert_authoritative_lease,
    assert_commit_matches_candidate,
    assert_epoch_fencing,
    assert_fingerprint_unchanged,
    assert_no_new_control_plane_paths,
    cas_promote_guard,
    create_ephemeral_workspace,
    create_governed_commit,
    inspect_changed_paths,
    list_control_plane_dirty,
    promote_result,
    quarantine_violation,
    snapshot_workspace_fingerprint,
    validate_paths_against_scope,
)
from governed_ai.core.execution_gateway.validation import (
    assert_agent_status_promotable,
    assert_identity_match,
    require_valid_capabilities,
    require_valid_request,
    require_valid_result,
)
from governed_ai.core.execution_gateway.verification import (
    load_profile_commands,
    run_profile_verifications,
)
from governed_ai.core.orchestrator.git_workspace import GitWorkspaceError, head_sha
from governed_ai.core.supervisor import journal
from governed_ai.core.supervisor.file_lock import exclusive_file_lock
from governed_ai.core.supervisor.paths import queue_dir
from governed_ai.core.workspace import Workspace

DEFAULT_ROLE_PROCEDURES: dict[str, set[str]] = {
    "backend-developer": {"implement-work-unit"},
    "frontend-developer": {
        "implement-work-unit",
        "frontend-design",
        "implement-approved-design",
        "adapt-approved-design",
        "create-frontend-design",
    },
    "qa-test": {"webapp-testing", "design-verification"},
    "code-reviewer": {"webapp-testing", "challenge-requirements"},
    "security-reviewer": {"security-review"},
    "auditor": {"audit-release"},
    "integration-steward": {"integrate-work-units"},
    "product-designer": {
        "create-frontend-design",
        "adapt-approved-design",
        "design-change-reconciliation",
    },
    "design-system-steward": {"design-system-integration"},
    "visual-qa": {"visual-conformance-review"},
    "control-plane": set(),
    "architect": set(),
    "mandate-matcher": {"match-mandate"},
    "requirements-challenger": {"challenge-requirements"},
    "test-strategist": {"webapp-testing"},
    "release-agent": {"audit-release"},
}


class AdapterLike(Protocol):
    def execute(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class GatewayOutcome:
    status: str
    result: ExecutionResult | None = None
    error: StructuredError | None = None
    promoted_sha: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    context_package: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "accepted" and self.error is None


@dataclass
class AgentExecutionGateway:
    """Canonical Core↔adapter boundary used by the orchestrator and supervisor."""

    workspace: Workspace
    legacy_adapter: LegacyExecutionResultAdapter = field(
        default_factory=LegacyExecutionResultAdapter
    )
    # Optional in-memory context packages keyed by hash (transmitted package).
    _context_packages: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    def compile_request(
        self,
        *,
        execution_id: str,
        run_id: str,
        work_unit: dict[str, Any],
        lease_id: str,
        epoch: int,
        role_id: str | None = None,
        procedure_id: str,
        base_sha: str,
        grant_allowed_paths: list[str],
        allowed_shell_commands: list[str],
        required_checks: list[str],
        capabilities: CapabilityDescriptor | dict[str, Any],
        context_role: str | None = None,
        fallback_role: str | None = None,
        role_procedures: dict[str, set[str]] | None = None,
        known_roles: set[str] | frozenset[str] | None = None,
        supported_combinations: set[tuple[str, str]] | frozenset[tuple[str, str]] | None = None,
        adapter_id: str = "external",
        accessible_secrets: list[str] | None = None,
        profile: dict[str, Any] | None = None,
        role_write_paths: list[str] | None = None,
        adapter_paths: list[str] | None = None,
        execution_ceiling_paths: list[str] | None = None,
        grant_axis_present: bool = True,
    ) -> tuple[ExecutionRequest, dict[str, Any]]:
        """Compile contract + context; refuse contradictions before launch."""
        require_valid_capabilities(dict(capabilities))
        resolved_role = role_id or resolve_role(
            work_unit=work_unit,
            context_role=context_role,
            fallback_role=fallback_role,
        )
        compiled_roles = set(known_roles) if known_roles is not None else set(DEFAULT_ROLE_PROCEDURES)
        compiled_procedures = (
            {key: set(value) for key, value in role_procedures.items()}
            if role_procedures is not None
            else {key: set(value) for key, value in DEFAULT_ROLE_PROCEDURES.items()}
        )
        assert_role_procedure(
            role_id=resolved_role,
            procedure_id=procedure_id,
            known_roles=compiled_roles,
            role_procedures=compiled_procedures,
            supported_combinations=supported_combinations,
        )
        assert_capabilities(
            capabilities,
            role_id=resolved_role,
            procedure_id=procedure_id,
        )
        # Role/procedure must be an explicit combination — never the Cartesian
        # product of separate supported_roles × supported_procedures lists.
        roles = set(capabilities.get("supported_roles") or [])
        procedures = set(capabilities.get("supported_procedures") or [])
        combinations = capabilities.get("supported_role_procedures")
        if combinations is not None:
            allowed_pairs = {
                (str(item[0]), str(item[1]))
                for item in combinations
                if isinstance(item, (list, tuple)) and len(item) == 2
            }
        else:
            # Derive pairs from bundle attachments ∩ adapter capability lists.
            allowed_pairs = {
                (role, proc)
                for role, procs in compiled_procedures.items()
                if role in roles
                for proc in procs
                if proc in procedures
            }
        if (resolved_role, procedure_id) not in allowed_pairs:
            raise ExecutionGatewayError(
                StructuredError(
                    code="unsupported_procedure",
                    message=(
                        f"combination ({resolved_role!r}, {procedure_id!r}) is not "
                        "an explicitly supported role/procedure pair"
                    ),
                    path="capabilities.supported_role_procedures",
                )
            )

        design_context = None
        binding = work_unit.get("design_binding")
        if isinstance(binding, dict) and binding.get("design_contract_id"):
            from governed_ai.core.design_authority.context import (
                build_multimodal_design_context,
            )
            from governed_ai.core.design_authority.procedure_select import (
                assert_procedure_matches_binding,
            )
            from governed_ai.core.design_authority.visual_capabilities import (
                assert_visual_capabilities,
            )

            assert_procedure_matches_binding(work_unit, procedure_id)
            design_context = build_multimodal_design_context(
                self.workspace, work_unit=work_unit
            )
            references = []
            if design_context:
                for ref in design_context.get("references") or []:
                    path = str(ref.get("source_path") or "").lower()
                    uri = str(ref.get("source_uri") or "")
                    source_type = None
                    if path.endswith(".pdf"):
                        source_type = "pdf"
                    elif path.endswith(".svg"):
                        source_type = "svg"
                    elif path.endswith((".png", ".jpg", ".jpeg", ".webp")):
                        source_type = "screenshot"
                    elif "figma.com" in uri:
                        source_type = "figma_link"
                    references.append(
                        {
                            "authority_level": ref.get("authority_level"),
                            "source_path": ref.get("source_path"),
                            "source_uri": ref.get("source_uri"),
                            "source_type": source_type,
                        }
                    )
            assert_visual_capabilities(capabilities, references=references)

        cap_write_present = "filesystem_write_paths" in capabilities
        cap_write = list(capabilities.get("filesystem_write_paths") or [])
        resolved_adapter_paths: list[str] | None
        if adapter_paths is not None:
            resolved_adapter_paths = adapter_paths
        elif cap_write_present:
            resolved_adapter_paths = cap_write
        else:
            resolved_adapter_paths = None
        scope = compute_effective_scope(
            work_unit=work_unit,
            grant_allowed_paths=grant_allowed_paths,
            role_write_paths=role_write_paths,
            adapter_paths=resolved_adapter_paths,
            execution_ceiling_paths=execution_ceiling_paths,
            grant_axis_present=grant_axis_present,
        )
        # Build the final immutable contract first, then hash the package on it.
        contract: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract_id": f"CTR-{execution_id}",
            "role_id": resolved_role,
            "procedure_id": procedure_id,
            "effective_scope": list(scope["include"]),
            "excluded_paths": list(scope["exclude"]),
            "required_checks": list(required_checks),
            "allowed_shell_commands": list(allowed_shell_commands),
            "accessible_secrets": list(accessible_secrets or []),
            "max_artifact_bytes": MAX_ARTIFACT_BYTES,
        }
        context = compile_context_package(
            contract=contract,
            role_id=resolved_role,
            procedure_id=procedure_id,
            work_unit=work_unit,
            acceptance_criteria=list(work_unit.get("acceptance_criteria") or []),
            required_checks=list(required_checks),
            effective_scope=scope,
            constraints={"profile_commands": load_profile_commands(profile or {})},
            design_context=design_context,
        )
        # Persist the hash onto a deep-copied contract that matches the package.
        contract = copy.deepcopy(context["contract"])
        contract["context_package_hash"] = context["context_package_hash"]
        # Re-hash after embedding the hash into the request contract only if the
        # package contract itself does not include context_package_hash.
        assert_package_hash_matches(context, context["context_package_hash"])
        self._context_packages[context["context_package_hash"]] = copy.deepcopy(context)
        request: ExecutionRequest = {
            "schema_version": SCHEMA_VERSION,
            "execution_id": execution_id,
            "run_id": run_id,
            "work_unit_id": str(work_unit.get("id") or ""),
            "lease_id": lease_id,
            "epoch": epoch,
            "role_id": resolved_role,
            "procedure_id": procedure_id,
            "base_sha": base_sha,
            "context_package_ref": str(work_unit.get("context_package_ref") or ""),
            "context_package_hash": context["context_package_hash"],
            "contract": contract,  # type: ignore[typeddict-item]
            "adapter_id": adapter_id,
        }
        require_valid_request(request)
        return request, context

    def execute(
        self,
        *,
        request: ExecutionRequest | dict[str, Any],
        adapter: AdapterLike,
        work_unit: dict[str, Any],
        grant_allowed_paths: list[str],
        profile: dict[str, Any] | None = None,
        use_ephemeral_workspace: bool = True,
        execution_workspace: Path | None = None,
        run_independent_verification: bool = True,
        instance_id: str = "gateway",
        worker_id: str | None = None,
        context_package: dict[str, Any] | None = None,
        fence_authoritative_lease: bool = True,
        role_write_paths: list[str] | None = None,
    ) -> GatewayOutcome:
        """Full transactional cycle: invoke adapter → verify → promote or reject."""
        events: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        require_valid_request(request)
        execution_id = str(request["execution_id"])
        run_id = str(request["run_id"])
        work_unit_id = str(request["work_unit_id"])
        lease_id = str(request["lease_id"])
        base_sha = str(request["base_sha"])
        epoch = request["epoch"]
        role_id = str(request["role_id"])
        procedure_id = str(request["procedure_id"])
        expected_context_hash = str(request.get("context_package_hash") or "")

        transmitted = context_package or self._context_packages.get(expected_context_hash)
        if transmitted is not None:
            recalculated = hash_context_package(transmitted)
            if recalculated != expected_context_hash:
                return GatewayOutcome(
                    status="rejected",
                    error=StructuredError(
                        code="context_hash_mismatch",
                        message="transmitted context package hash mismatch",
                        path="context_package_hash",
                        details={"expected": expected_context_hash, "recalculated": recalculated},
                    ),
                    events=events,
                )

        events.append(
            make_progress_event(
                ProgressEventType.PROCESS_STARTED,
                execution_id=execution_id,
                run_id=run_id,
                work_unit_id=work_unit_id,
            )
        )

        ephemeral: Path | None = None
        claim_path: Path | None = None
        canonical: ExecutionResult | None = None
        persisted_evidence_paths: list[Path] = []
        try:
            if use_ephemeral_workspace:
                git_root = Path(execution_workspace or self.workspace.root)
                ephemeral = create_ephemeral_workspace(
                    git_root,
                    base_sha=base_sha,
                    execution_id=execution_id,
                    worktree_home=self.workspace.instance_root,
                )
                root = ephemeral
                adapter_request = dict(request)
                adapter_request["execution_workspace"] = str(ephemeral)
            else:
                root = execution_workspace or self.workspace.root
                adapter_request = dict(request)
                adapter_request["execution_workspace"] = str(root)

            if transmitted is not None:
                adapter_request["context_package"] = copy.deepcopy(transmitted)

            events.append(
                make_progress_event(
                    ProgressEventType.CONTEXT_LOADED,
                    execution_id=execution_id,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    payload={"context_package_hash": expected_context_hash},
                )
            )
            events.append(
                make_progress_event(
                    ProgressEventType.MODIFICATION_STARTED,
                    execution_id=execution_id,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                )
            )

            # Snapshot Control-Plane dirtiness before the adapter so pre-existing
            # untracked grant/state files are not attributed to the agent.
            preexisting_cp = list_control_plane_dirty(root)
            raw = adapter.execute(adapter_request)
            canonical = self.legacy_adapter.adapt(raw, request=request)
            # Ensure required result fields exist before strict validation.
            canonical.setdefault("requested_commands", [])
            canonical.setdefault("limitations", [])
            canonical.setdefault("usage", {})
            canonical.setdefault("provider_metadata", {})
            canonical.setdefault("context_package_hash", expected_context_hash)
            require_valid_result(canonical)
            assert_identity_match(request, canonical)
            assert_epoch_fencing(
                request_epoch=epoch,
                result_epoch=canonical.get("epoch"),
            )
            assert_context_hash(
                canonical.get("context_package_hash") or raw.get("context_package_hash"),
                expected_context_hash,
            )
            assert_agent_status_promotable(str(canonical.get("status") or ""))

            contract = request.get("contract") or {}
            allowlist = list(contract.get("allowed_shell_commands") or [])
            assert_requested_commands_allowed(
                list(canonical.get("requested_commands") or []),
                allowlist,
            )

            try:
                observed_head = head_sha(root)
            except GitWorkspaceError as exc:
                raise ExecutionGatewayError(
                    StructuredError(
                        code="git_head_unreadable",
                        message=str(exc),
                        path="workspace.observed_head_sha",
                    )
                ) from exc

            claimed = (canonical.get("workspace") or {}).get("claimed_result_sha") or (
                (raw.get("workspace") or {}).get("result_sha")
            )
            # Always compare claimed SHA to observed HEAD — including ephemeral mode.
            if claimed:
                if str(claimed) != str(observed_head):
                    raise ExecutionGatewayError(
                        StructuredError(
                            code="result_sha_mismatch",
                            message="claimed result_sha does not match observed HEAD",
                            path="workspace.result_sha",
                            details={"claimed": claimed, "observed": observed_head},
                        )
                    )

            # --- Capture candidate (1) + hashes (2) ---
            assert_no_new_control_plane_paths(root, preexisting=preexisting_cp)
            files = inspect_changed_paths(
                root,
                base_sha,
                preexisting_control_plane=preexisting_cp,
            )
            events.append(
                make_progress_event(
                    ProgressEventType.FILES_INSPECTED,
                    execution_id=execution_id,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    payload={"files": files[:100]},
                )
            )
            validate_paths_against_scope(
                files,
                work_unit_id=work_unit_id,
                work_unit=work_unit,
                allowed_paths=grant_allowed_paths,
                workspace_root=root,
                role_write_paths=role_write_paths,
            )
            fingerprint = snapshot_workspace_fingerprint(root, files)

            verified_artifacts = []
            for artifact in canonical.get("artifacts") or []:
                path = str(artifact.get("path") or "")
                if not path:
                    continue
                verified = verify_artifact(
                    root,
                    path=path,
                    agent_reported_sha256=artifact.get("agent_reported_sha256")
                    or artifact.get("sha256"),
                    max_bytes=MAX_ARTIFACT_BYTES,
                )
                verified_artifacts.append(verified)

            # --- Independent verifications (3) ---
            independent: list[dict[str, Any]] = []
            if run_independent_verification and profile:
                events.append(
                    make_progress_event(
                        ProgressEventType.VERIFICATION_STARTED,
                        execution_id=execution_id,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                    )
                )
                for command in allowlist:
                    assert_command_allowed(command, allowlist)
                independent = list(
                    run_profile_verifications(
                        workspace_root=root,
                        profile_commands=load_profile_commands(profile),
                        allowlist=allowlist or None,
                        timeout_seconds=float(contract.get("timeout_seconds") or 60),
                        secrets_to_redact=list(contract.get("accessible_secrets") or []),
                    )
                )
                failed = [item for item in independent if item.get("status") != "passed"]
                if failed:
                    raise ExecutionGatewayError(
                        StructuredError(
                            code="independent_verification_failed",
                            message="framework verification runner reported failures",
                            path="verification",
                            details={"failed": [item.get("canonical_id") for item in failed]},
                        )
                    )
                events.append(
                    make_progress_event(
                        ProgressEventType.VERIFICATION_COMPLETED,
                        execution_id=execution_id,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                        payload={"checks": [item.get("canonical_id") for item in independent]},
                    )
                )

            # --- Full re-inspect (4–6) ---
            assert_no_new_control_plane_paths(root, preexisting=preexisting_cp)
            rechecked = inspect_changed_paths(
                root,
                base_sha,
                preexisting_control_plane=preexisting_cp,
            )
            validate_paths_against_scope(
                rechecked,
                work_unit_id=work_unit_id,
                work_unit=work_unit,
                allowed_paths=grant_allowed_paths,
                workspace_root=root,
                role_write_paths=role_write_paths,
            )
            assert_fingerprint_unchanged(root, fingerprint)
            if set(rechecked) != set(files):
                raise ExecutionGatewayError(
                    StructuredError(
                        code="workspace_mutated_after_verification",
                        message="changed path set diverged after verification",
                        path="workspace.diff",
                        details={"before": files, "after": rechecked},
                    )
                )
            # Re-hash artifacts after re-inspect.
            verified_artifacts = []
            for artifact in canonical.get("artifacts") or []:
                path = str(artifact.get("path") or "")
                if not path:
                    continue
                verified = verify_artifact(
                    root,
                    path=path,
                    agent_reported_sha256=artifact.get("agent_reported_sha256")
                    or artifact.get("sha256"),
                    max_bytes=MAX_ARTIFACT_BYTES,
                )
                verified_artifacts.append(verified)
                manifest = build_evidence_manifest(
                    source="artifact",
                    trust_level=str(verified.get("trust_level") or "framework_observed"),  # type: ignore[arg-type]
                    producer="agent",
                    verifier="execution_gateway",
                    content_hash=verified.get("observed_sha256"),
                    artifact_path=path,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    execution_id=execution_id,
                    canonical_check_id="implementation",
                )
                evidence.append(manifest)

            # Satisfy required checks using agent reports ∪ independent results.
            required = list(contract.get("required_checks") or [])
            reported = [
                str(item.get("reported_name") or item.get("canonical_id") or "")
                for item in (canonical.get("checks") or [])
                if str(item.get("status") or "") == "passed"
            ]
            for item in independent:
                if item.get("status") == "passed":
                    reported.append(str(item.get("canonical_id") or ""))
            satisfied, rejected, missing = resolve_required_checks(reported, required=required)
            if missing:
                raise ExecutionGatewayError(
                    StructuredError(
                        code="required_checks_unsatisfied",
                        message=f"missing required checks: {missing}",
                        path="checks",
                        details={"rejected_aliases": rejected, "satisfied": sorted(satisfied)},
                    )
                )

            independent_by_id = {
                str(item.get("canonical_id")): item
                for item in independent
                if item.get("status") == "passed"
            }
            configured_verifications = load_profile_commands(profile or {})
            for check in canonical.get("checks") or []:
                raw_name = str(check.get("reported_name") or check.get("canonical_id") or "")
                canonical_id = normalize_check_name(raw_name) or str(check.get("canonical_id") or "")
                if not canonical_id:
                    continue
                definition = assert_check_authorized(
                    canonical_id=canonical_id,
                    role_id=role_id,
                    procedure_id=procedure_id,
                )
                blocking = registry_blocking(canonical_id, fallback=True)
                # diff_scope is satisfied by the gateway's own path inspection.
                if definition.independent_verification == "diff_scope":
                    continue
                verification_field = definition.independent_verification
                can_verify = bool(
                    verification_field
                    and (
                        configured_verifications.get(verification_field)
                        or (
                            verification_field == "unit_test"
                            and configured_verifications.get("integration_test")
                        )
                    )
                )
                covered = canonical_id in independent_by_id
                if blocking and can_verify and not covered:
                    assert_blocking_check_trust(
                        {**check, "canonical_id": canonical_id, "blocking": True},
                        can_verify=True,
                    )

            # --- Authoritative epoch fence + atomic promotion (7–8) ---
            # Command Gateway lease updates use project.lock; supervisor queue
            # lease updates use queue.lock. Holding both across the final read,
            # commit-object verification, evidence persistence, and promotion
            # prevents an epoch change from interleaving with acceptance.
            project_lock = None
            with ExitStack() as promotion_stack:
                if fence_authoritative_lease:
                    # Local import avoids the persistence.lock → commands
                    # package initialization cycle at module import time.
                    from governed_ai.core.persistence.lock import acquire_project_lock

                    project_lock = acquire_project_lock(
                        self.workspace.ai_team / "locks" / "project.lock"
                    )
                    promotion_stack.callback(project_lock.release)
                    promotion_stack.enter_context(
                        exclusive_file_lock(
                            queue_dir(self.workspace.ai_team) / "queue.lock",
                            timeout_seconds=15.0,
                        )
                    )
                    assert_authoritative_lease(
                        self.workspace.ai_team,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                        lease_id=lease_id,
                        epoch=epoch,
                        worker_id=worker_id,
                    )
                    claim_path = cas_promote_guard(
                        self.workspace.ai_team,
                        execution_id=execution_id,
                        lease_id=lease_id,
                        epoch=epoch,
                    )
                    assert_authoritative_lease(
                        self.workspace.ai_team,
                        run_id=run_id,
                        work_unit_id=work_unit_id,
                        lease_id=lease_id,
                        epoch=epoch,
                        worker_id=worker_id,
                    )

                promoted = create_governed_commit(
                    root,
                    work_unit_id=work_unit_id,
                    execution_id=execution_id,
                    paths=rechecked,
                )
                assert_commit_matches_candidate(
                    root,
                    base_sha=base_sha,
                    promoted_sha=promoted,
                    validated_paths=rechecked,
                    artifact_hashes={
                        str(item["path"]): str(item["observed_sha256"])
                        for item in verified_artifacts
                        if item.get("path") and item.get("observed_sha256")
                    },
                )
                # Evidence becomes durable only after the final authoritative
                # fence and after its bytes have been checked against the
                # immutable commit object.
                for manifest in evidence:
                    persisted_evidence_paths.append(
                        persist_evidence_manifest(self.workspace.ai_team, manifest)
                    )
                # Never silently replace a false claimed SHA; Core SHA always
                # wins for promotion.
                if use_ephemeral_workspace and ephemeral is not None:
                    promote_result(
                        project_root=self.workspace.root,
                        ephemeral_root=ephemeral,
                        execution_id=execution_id,
                        promoted_sha=promoted,
                    )

            workspace_meta = dict(canonical.get("workspace") or {})
            workspace_meta.update(
                {
                    "schema_version": SCHEMA_VERSION,
                    "base_sha": base_sha,
                    "claimed_result_sha": claimed,
                    "observed_head_sha": promoted,
                    "promoted_sha": promoted,
                    "trust_level": "framework_verified",
                    "resumable": True,
                }
            )
            canonical["workspace"] = workspace_meta  # type: ignore[typeddict-item]
            canonical["artifacts"] = verified_artifacts  # type: ignore[typeddict-item]
            if independent:
                merged_checks = list(canonical.get("checks") or []) + independent
                canonical["checks"] = merged_checks  # type: ignore[typeddict-item]
            # Preserve agent succeeded — never coerce failed/blocked into succeeded.
            canonical["status"] = "succeeded"

            events.append(
                make_progress_event(
                    ProgressEventType.RESULT_SUBMITTED,
                    execution_id=execution_id,
                    run_id=run_id,
                    work_unit_id=work_unit_id,
                    payload={"promoted_sha": promoted},
                )
            )
            journal.append_event(
                self.workspace.ai_team,
                instance_id=instance_id,
                event_type="execution_accepted",
                run_id=run_id,
                work_unit_id=work_unit_id,
                payload={"execution_id": execution_id, "promoted_sha": promoted},
            )
            return GatewayOutcome(
                status="accepted",
                result=canonical,
                promoted_sha=promoted,
                events=events,
                evidence=evidence,
                context_package=transmitted,
            )
        except ExecutionGatewayError as exc:
            for evidence_path in persisted_evidence_paths:
                evidence_path.unlink(missing_ok=True)
            if claim_path is not None:
                claim_path.unlink(missing_ok=True)
            if ephemeral is not None:
                quarantine_violation(
                    project_root=self.workspace.root,
                    ephemeral_root=ephemeral,
                    execution_id=execution_id,
                    reason=exc.error.message,
                    files=[],
                    last_healthy_sha=base_sha,
                )
            journal.append_event(
                self.workspace.ai_team,
                instance_id=instance_id,
                event_type="execution_rejected",
                run_id=run_id,
                work_unit_id=work_unit_id,
                payload={"execution_id": execution_id, "error": exc.error.to_dict()},
            )
            return GatewayOutcome(
                status="rejected",
                result=canonical,
                error=exc.error,
                events=events,
                evidence=[],
            )
