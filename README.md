# Governed AI Development Team Framework

*[Lire en français](README.fr.md)*

A GitHub-ready framework for running a **human-governed, multi-agent software development team in Cursor**.

This repository materializes an AI engineering organization as version-controlled policy, roles, Work Units, project state, evidence, review, audit, permissions, and human gates.

## Core operating principle

The framework separates:

1. **Human construction material** — what must be built: product intent, scope, business rules, requirements, architecture, constraints, acceptance criteria.
2. **Engineering Constitution** — how the AI organization is allowed to operate: authority, decomposition, context, staffing, permissions, testing, review, audit, release, and human gates.
3. **Execution state** — the derived, inspectable runtime model: Project State, Work Units, dependencies, evidence, findings, decisions, release candidates, and acceptance results.

The AI team may analyze, propose, implement, test, review, and audit. It may **not silently invent missing product decisions or change its own Constitution**.

## What is already implemented in this repository

- Cursor Project Rules in `.cursor/rules/`
- Cursor custom subagents in `.cursor/agents/`
- Cursor Agent Skills in `.cursor/skills/`
- Cursor project hooks in `.cursor/hooks.json`
- Cursor per-repository execution guidance in `.cursor/permissions.json`
- Cursor Bugbot rules in `.cursor/BUGBOT.md`
- Engineering Constitution in `.ai-team/constitution/`
- JSON Schemas for all core state objects in `.ai-team/schemas/`
- Ready-to-use templates in `.ai-team/templates/`
- Runtime directories for Work Units, decisions, evidence, findings, audit, release and acceptance
- Validation and status tooling in `scripts/ai-team/`
- Cross-platform installer in `tools/install.py`
- An optional, non-installed reference example in `examples/project-a/`

## Quickstart

### 1. Install into your project

Clone this framework anywhere, then run it against your target repository:

```bash
python tools/install.py \
  --target /path/to/your/project \
  --project-id project-a \
  --project-name "Project A"
```

`install.py` never overwrites a file that already exists in the target
unless you pass `--force`, and it never copies `examples/`.

### 2. Fill in what only you know

Two files, both under `.ai-team/`, need real values before you compile
anything — everything else is already usable as shipped:

- **`.ai-team/project-profile.yaml`** — your real build/lint/test commands,
  source/test paths, and who holds product / Constitution / release /
  acceptance authority on this project. Open the file: a commented example
  is right at the top.
- **`.ai-team/sources/source-registry.yaml`** — one entry per authoritative
  product document you're about to drop under `docs/product/`. Same pattern:
  a commented example is at the top of the file.

Then check what, if anything, is still missing:

```bash
python scripts/ai-team/validate.py
```

This only ever reports on the two files above (and on the Work Units you'll
create later) — it does not ask you to touch the Constitution defaults.

### 3. Open the project in Cursor

Open the installed project (not this framework repo) in Cursor, and make
sure the workspace is trusted. Cursor discovers `.cursor/rules/`,
`.cursor/agents/`, `.cursor/skills/` and `.cursor/hooks.json` on workspace
open; if a `/`-command you expect doesn't show up, restart Cursor once.

### 4. Compile the project

In the Cursor Agent, explicitly invoke the Skill — it is deliberately not
auto-triggered, so opening Cursor never silently starts the team:

```text
/compile-project

Compile the project from @docs/product/. Do not implement any product code —
stop after producing the execution plan for my approval.
```

This reads your registered sources and the Constitution, and produces (or
updates) `.ai-team/state/project-state.yaml` and `.ai-team/work-units/*.yaml`
— a dependency graph, risk classes, required verification, a context plan
and a staffing proposal. No product code is touched.

### 5. Inspect and approve G1

```bash
python scripts/ai-team/status.py
```

Read the proposed Work Units and staffing. When you're satisfied:

```bash
python scripts/ai-team/record_gate.py G1 approved --by YOUR_NAME --note "Execution plan approved"
```

### 6. Start the orchestrator

```text
/orchestrator
```

Use it as a Custom Mode to keep it active for the session. It activates
specialist subagents only for Work Units that are ready, within the WIP
limits below — never all of them at once.

Looking for a concrete, already-compiled Work Unit to see the expected shape
before you run your own? See `examples/project-a/` — read-only reference,
not something you install or clean up.

## Recommended default operating profile

This repository ships with an **opinionated reference profile**:

- Autonomy: Level 2 — semi-autonomous team
- Max active Work Units: 3
- Max concurrent code-writing workers: 2
- Max concurrent high/critical-risk Work Units: 1
- One primary writer per Work Unit
- Reviewer: read-only
- Security reviewer: read-only
- Auditor: read-only and independent from remediation
- Production release: human gate G3
- Final acceptance: human gate G4

These are implementation defaults, not universal truths. Change them in the Constitution and version the change.

## Runtime flow

```text
Human product material + Engineering Constitution
                    |
                    v
               Readiness G0
                    |
                    v
              Project Compiler
                    |
                    v
      Project State + Work Units + plan
                    |
                    v
             Human approval G1
                    |
                    v
               Orchestrator
        +-----------+-----------+
        |           |           |
     Developer      QA       Reviewer
        |           |           |
        +-----------+-----------+
                    |
                    v
             Independent Audit
                    |
                    v
          Release Candidate / G3
                    |
                    v
             Human Acceptance G4
                    |
                    v
                   Done
```

## Important security note

Cursor rules, prompts, hooks, and `permissions.json` are **governance controls, not a complete security boundary**. Keep branch protection, CI checks, environment protection, secrets, deployment credentials, CODEOWNERS, and production IAM outside the model and enforce them in Git hosting / CI / cloud infrastructure.

See `docs/SECURITY_MODEL.md`.

## Going further

- Full checklist before running on a real project: `docs/ADOPTER_CHECKLIST.md`.
- Step-by-step operator reference (also available in French): `docs/OPERATOR_GUIDE.fr.md`.
- Architecture, state machine and review pipeline: `docs/ARCHITECTURE.md`.
- What Cursor governance controls do and don't cover: `docs/SECURITY_MODEL.md`.
- Where each part of this repository maps back to the base design document: `docs/SOURCE_MAPPING.md`.

## License

MIT. See `LICENSE`.
