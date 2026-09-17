---
name: reconcile-project
description: Reconcile sufficient authoritative human material with an existing project's observed implementation, apply only an approved convergence plan, verify the result, and establish the baseline required by /compile-project.
disable-model-invocation: true
icon: git-compare-arrows
color: orange
---
# Reconcile Project

## Framework source guard

Read `.ai-team/project-profile.yaml` → `project.repository_kind` first.

When `repository_kind` is `framework_source`, **stop immediately**. This command
is only for installed client projects.

This operation prepares a project for compilation. It does not create Work Units,
set G1, or run `/compile-project`.

## Start or resume

1. Run `python scripts/ai-team/reconcile_project.py init` when
   `.ai-team/reconciliation/baseline.yaml` does not exist.
2. When the report exists, resume it. Never replace it with `--force` unless the
   human explicitly requests a new reconciliation.
3. Read:
   - `.ai-team/constitution/`;
   - `.ai-team/project-profile.yaml`;
   - `.ai-team/sources/source-registry.yaml`;
   - every registered authoritative product source;
   - `.ai-team/reconciliation/baseline.yaml`;
   - repository content as observed reality only.

## Phase 1 — human material

Assess and reference authoritative sources for:

- objectives and expected outcomes;
- users and actors;
- business rules and invariants;
- functional, non-functional, security, compliance, and architecture constraints;
- explicit in-scope and out-of-scope boundaries;
- prior human decisions;
- observable acceptance criteria.

Mark material `sufficient` only with at least one authoritative `source_ref` using
an active human source ID from `.ai-team/sources/source-registry.yaml`.
Use `not_applicable` sparingly and explain it in `note`. Missing or contradictory
material remains blocking; create a structured decision request and set the report
to `awaiting_decisions`.

## Phase 2 — as-built inventory and comparison

Inspect code, architecture, tests, data and migrations, dependencies,
documentation, infrastructure, and technical debt. Enrich the structural inventory
created by the script with evidence that is relevant to the reconciled scope.

For each material surface, add one convergence item and classify it as:

- `conformant`;
- `adapt`;
- `obsolete_out_of_scope`;
- `conflicting`;
- `undetermined`.

Link the comparison to human `intent_refs`. Existing code never becomes product
intent merely because it exists.

## Phase 3 — convergence plan and approval

Assign exactly one action to each item: `keep`, `migrate`, `rewrite`, `isolate`,
`delete`, or `clarify`. Make the intended path scope and verification explicit in
the item.

Present the complete plan before applying it. Every `migrate`, `rewrite`, `isolate`,
or `delete` action requires explicit human approval recorded as
`human_approval_ref`. Without it, stop; do not mutate that surface.

Prefer recoverable changes and preserve repository history. Do not broaden the
approved scope, reinterpret human intent, or silently remove apparently unused
content.

## Phase 4 — apply and verify

After approval:

1. Set the report status to `applying`.
2. Delegate approved product changes to the `reconciliation-steward`; apply only
   the approved convergence actions.
3. Record each result as `completed`, or `waived` with its human decision reference.
4. Run every relevant command declared by the project profile plus focused checks
   for migrations and cleanup.
5. Record commands, status, and evidence under `verification.commands`.
6. Keep failed or required-but-unrun checks blocking.
7. Set `verification.blocking_conflicts` to the exact number of convergence items
   not `completed` or `waived`.

## Phase 5 — establish the baseline

When all material is sufficient, all decisions are resolved, every convergence
item is terminal, and verification passes:

1. Set the report status to `approved`.
2. Run `python scripts/ai-team/reconcile_project.py finalize`.
3. Run `python scripts/ai-team/reconcile_project.py check` and report the result.
4. Stop. Tell the human that `/compile-project` is now permitted.

The finalizer computes the project-owned content fingerprint and is the only step
that sets status `ready`. Any later project-owned content change makes this baseline
stale and requires reconciliation to be resumed before compilation.

## Required outputs

- sufficient human-material assessment with source references;
- as-built inventory;
- complete convergence matrix;
- recorded human decisions and approvals;
- evidence for applied changes;
- passing verification results;
- current `ready` reconciliation baseline.
