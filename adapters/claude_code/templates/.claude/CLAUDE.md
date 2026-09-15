# Governed AI Team Instructions

This repository uses the Engineering Constitution under `.ai-team/constitution/`.

## Installed client project

Read `.ai-team/project-profile.yaml` and `.ai-team/state/project-state.yaml`
before runtime activation.

- Use `/reconcile-project` after install and whenever human sources or
  project-owned content change; `/compile-project` requires its current baseline.
- Use `/compile-project` after reconciliation when no approved execution plan
  exists or after material human source changes.
- Product work is attributable to Work Units under `.ai-team/work-units/`.
- Respect human gates G0–G4 and the orchestrator Control Plane.
- Record reusable friction with `python scripts/ai-team/feedback.py record`
  on this installed target when appropriate.
- Inspect SMTP readiness with `python scripts/ai-team/notify.py status`; delivery
  failures stay non-blocking and credentials must remain under
  `.ai-team/secrets/` or in environment variables.
- Follow `.ai-team/constitution/95-git-release-policy.yaml` for branches,
  commits, evidence, and merge discipline.

Do not invent missing product or policy decisions. Treat repository state and
runtime evidence as observed reality, not as permission to contradict human
authoritative sources under `docs/product/` and `.ai-team/sources/`.

## Core governance

The Engineering Constitution under `.ai-team/constitution/` is authoritative for agent operation.

Always preserve these invariants:

- Human sources define product intent and organizational policy.
- A missing decision remains visibly missing.
- An agent proposal is not a product or policy decision.
- The approved execution model is derived and may not contradict its human sources.
- Repository state is observed reality, not product authority.

## Framework source workspace layout

Read `.ai-team/project-profile.yaml` → `project.repository_kind` first.

When `repository_kind` is `framework_source`:

- This repository **builds** the framework. It is **not** an installed client
  project and must not be analyzed as one.
- `.ai-team/state/project-state.yaml` is a **virgin template** (`phase:
  not_compiled`, empty `work_units`). Do not treat it as an active client
  runtime or execution plan.
- Do **not** run `/compile-project`, gate commands, or client Work Unit cycles
  here. Framework development on this repo does not use the installed-client
  orchestration path.
- Edit implementation code under `src/governed_ai/`, `adapters/`, and
  `distribution/`. Never create `.ai-team/runtime/` or
  `installation-record.json` here.
- To observe installed behavior, use `tests/fixtures/projects/clean/` or
  `python tools/install.py --target <dir>` in a separate directory.
- Do not run `scripts/ai-team/feedback.py` record, retrospective, or export here.

When `repository_kind` is not `framework_source`, ignore the rules above.

## Work Unit discipline

When `.ai-team/project-profile.yaml` declares `repository_kind: framework_source`,
this rule does **not** apply. The source repository builds the framework; it does
not run the installed-client Work Unit cycle. See "Framework source workspace layout" above.

Product changes on an **installed client project** must be attributable to a Work
Unit in `.ai-team/work-units/`.

A Work Unit must have:
- stable ID and title;
- objective and scope;
- observable expected behavior;
- applicable rules/requirements;
- acceptance criteria;
- dependencies;
- risk class;
- required verification;
- Context Package reference;
- status.

Do not collapse definition, execution events, and outcomes into one free-form narrative.

If a Work Unit is not READY, do not start implementation. If an unknown requires human authority, emit a `DECISION_REQUEST` and block only dependent nodes.

## Evidence first

A claim that something works is not evidence.

Verification evidence must identify, as applicable:
- the exact code revision / commit;
- command or observation performed;
- result;
- behavior or acceptance criterion demonstrated;
- limitations such as mocks, stubs, unexecuted transport, unavailable environment, or partial coverage.

Never report "end-to-end verified" unless the relevant layers were actually executed and observed.

If the evaluated SHA changes after evidence is produced, invalidate the affected
evidence and rerun the relevant checks. Do not preserve a passing claim across an
amend, rebase, remediation commit, or any other revision change without new proof.

Auditors classify conclusions as:
- expected_and_observed;
- expected_but_not_demonstrated;
- observed_but_not_specified;
- contradiction;
- unknown.

## Least privilege

Respect role permissions in `.ai-team/constitution/70-permissions-policy.yaml`.

Never assume a prompt grants authority that infrastructure or policy does not grant.

High-impact actions require explicit authorization according to policy, including:
- secrets and credentials;
- permission / IAM changes;
- critical infrastructure changes;
- production data mutations;
- production deployment;
- direct protected-branch modification.

Developers may stage and commit coherent Work Unit changes without a separate
human confirmation only on an isolated, non-protected branch and only under
`95-git-release-policy.yaml` commit policy. History rewriting is not an
autonomous action.

Reviewer and Auditor roles must not silently remediate the code they are evaluating.

## Human gates

G0 — Readiness: insufficient or ambiguous authoritative inputs; on brownfield,
     also uninventoried as-built gaps (code vs intent, out-of-scope, cleanup)
     that would make the first compile incoherent. `/compile-project` must first
     pass the machine reconciliation check.
G1 — Execution plan: Project State and proposed plan must be approved before activating runtime.
G2 — Reserved decision: product decision, policy change, sensitive permission, or source conflict.
G3 — Release / production: protected environment deployment authorization.
G4 — Acceptance: human accepts, rejects, partially accepts, or requests remediation.

Batch non-urgent human questions where possible, including options, impact and evidence.
