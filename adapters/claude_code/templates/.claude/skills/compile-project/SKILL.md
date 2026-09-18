---
name: compile-project
description: Compile authoritative human product material and the Engineering Constitution into a readiness report, Project State, dependency graph, Work Units, risk, context plan and initial staffing. Must run before first runtime activation or after material source changes.
disable-model-invocation: true
icon: book-open
color: blue
---
# Compile Project

## Framework source guard

Read `.ai-team/project-profile.yaml` → `project.repository_kind` first.

When `repository_kind` is `framework_source`, **stop immediately**. This repository
builds the framework; it is not an installed client project. Do not run this skill
here, do not update `.ai-team/state/project-state.yaml` for a client cycle, and do
not create Work Units under `.ai-team/work-units/`. Framework work uses git branches,
review, and tests — see `AGENTS.md` and `05-workspace-layout.mdc`.

## Member checkout guard

If `.ai-team/member-link.json` exists here, **stop immediately**. This checkout is
an Ensemble member. Read `instance_path` from that file and run `/compile-project`
from the instance directory — never from the member Git.

This is a **planning-only** operation on installed client projects. Do not implement
product code.

## Required inputs

Read:
- `.ai-team/constitution/`
- `.ai-team/project-profile.yaml`
- `.ai-team/sources/source-registry.yaml`
- registered authoritative product sources
- `.ai-team/reconciliation/baseline.yaml` (standalone) or
  `.ai-team/ensembles/<ensemble-id>/reconciliation/baseline.yaml` when an
  Ensemble is active
- on an Ensemble: product intent under `docs/product/<ensemble-id>/` on the
  instance — never invent intent from a member Git
- repository only as observed reality when relevant

## Procedure

1. Run `python scripts/ai-team/reconcile_project.py check`. If it fails, stop
   and direct the human to `/reconcile-project`; never compile from a missing,
   incomplete, or stale reconciliation baseline.
2. Run Definition of Ready against the requested scope, including the
   brownfield `as_built_inventory` dimension when application code already
   exists.
3. Treat the repository as observed reality only. If code contradicts or
   exceeds human intent, report conformance gaps — do not rewrite intent from
   as-built code.
4. If blocking ambiguity exists (missing product material, unclear in/out of
   scope, uninventoried legacy/cleanup), emit G0 issues and stop the affected
   scope.
5. Build capabilities/features without inventing a new product structure.
6. Decompose into small, observable, testable Work Units — including explicit
   remediation / alignment / cleanup units for inventoried as-built gaps when
   humans have authorized that work in scope. On an Ensemble with two or more
   members, create one Work Unit per declared member with `member_id` set, plus
   one integration Work Unit (`kind: integration`, empty `scope.include`, no
   `member_id`) that depends on those member units and must not write product
   code.
7. Build explicit dependencies and identify the critical path.
8. Assign risk class from policy and record reasons.
9. Determine required verification from behavior + risk.
10. For frontend, fullstack and mobile Work Units, plan `human_ui_review`
    explicitly. Require one only for a first testable slice, new or critical
    journey, information-architecture change, high product ambiguity, or a
    material change to an already reviewed surface. Do not schedule it for
    invisible refactors or changes without user-perceptible effect. A planned
    checkpoint is formative and non-blocking; it is not G4 acceptance.
11. Build a Context Package plan for each Work Unit.
12. Propose staffing from staffing policy.
13. Update `.ai-team/state/project-state.yaml` and `.ai-team/work-units/`.
14. Run `python scripts/ai-team/propose_allowlist.py` and attach its output to
    the G1 decision package as a proposed allowlist diff — do not edit
    `.claude/settings.json` yourself (agents cannot write it; this is a
    proposal for the human to apply alongside the G1 decision, not a change
    you make).
15. Produce a concise execution-plan summary that states residual as-built
    gaps left out of scope (if any).
16. Set phase to `awaiting_g1_approval`.
17. STOP. Do not activate developers until a human records G1 approval.

## Required outputs

- readiness summary;
- verified current reconciliation baseline;
- generated/updated Work Units;
- dependency graph representation in Project State;
- risk and verification assignments;
- deliberately selected formative UI checkpoints, including their reason and surface;
- staffing proposal;
- proposed allowlist diff (from `scripts/ai-team/propose_allowlist.py`), for
  the human to review and apply — never applied automatically;
- unresolved decisions;
- G1 decision package.

## Invariant

`/compile-project` must never proceed when
`python scripts/ai-team/reconcile_project.py check` returns non-zero. A manual
claim that the repository is coherent does not replace the machine-readable,
content-fingerprinted baseline.

## YAML authoring

Every string value you write into a Work Unit (acceptance criteria,
applicable rules/requirements, expected behavior, etc.) that itself
contains a colon-space (`: `) or a curly brace (`{`/`}`) — for example
quoting an API path like `POST /api/tasks — create from { "title": "..." }`,
or describing a state like `when marked completed: true` — must be quoted
as a whole string (`"..."`) or written to avoid the ambiguous character
entirely. An unquoted colon or brace inside what looks like a plain YAML
scalar is parsed as the start of a nested mapping or flow object, and
breaks the file. Prefer writing such items as `{category}: {description}`
key-value structures where that's genuinely the intent (accepted by the
schema), or as a single fully-quoted string otherwise — never leave a
mid-sentence `:` or `{`/`}` unquoted.
