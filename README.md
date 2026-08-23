# Governed AI Development Team Framework

*[Lire en français](README.fr.md)*

This framework turns Cursor into a small, governed team of AI agents. Specialized subagents — developer, reviewer, security reviewer, auditor — work on narrowly scoped tasks under rules that live in version-controlled files in your repository, not in one giant prompt nobody re-reads.

Nothing is marked done without evidence: tests actually executed, a review completed, an independent audit where risk requires it. Product decisions and production releases stay with a human, at explicit approval points ("gates") the AI cannot skip.

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

## Requirements

- **Python 3.10 or later**, available on your PATH.
- Before installing, run `python --version`. If that command isn't found, try `python3 --version` instead.
  - If only `python3` works on your machine — common on macOS and on Linux
    distributions that don't ship a bare `python` — replace `python` with
    `python3` in every command shown in this guide, **and** in
    `.cursor/hooks.json`: Cursor runs the `command` string of every hook
    directly on your operating system's shell, using the exact interpreter
    name written there, so the hooks need whichever name actually resolves
    to Python 3 on your machine.
- Cursor, with your target project opened as a **trusted workspace** (see
  step 3 below).

## Quickstart

### 1. Install into your project

Clone this framework anywhere, then run the installer once against your
target repository. Replace `/path/to/your/project`, `your-project-id` and
`"Your Project Name"` below with your own project's actual path, id and
name — these are not values to leave as-is:

```bash
python tools/install.py --target /path/to/your/project --project-id your-project-id --project-name "Your Project Name"
```

This is written as one line on purpose so it can be pasted into any shell
unmodified. If you split it across multiple lines yourself, note that the
line-continuation character differs by shell: `\` on bash/zsh/Git Bash,
`^` on Windows `cmd.exe`, `` ` `` on PowerShell.

`install.py` never overwrites a file that already exists in the target
unless you pass `--force`, and it never copies `examples/`.

### 2. Fill in what only you know

Two files under `.ai-team/` are genuinely empty and need real values before
you compile anything. Everything else in the Constitution is already a
working default — you don't need to have read any external design document
to understand what goes in these two.

**`.ai-team/project-profile.yaml`** — open it and replace the placeholder
values. A commented example is at the top of the file; concretely, a filled
profile looks like this:

```yaml
project:
  id: checkout-service
  name: Checkout Service
paths:
  source_roots: [src]
  test_roots: [tests]
commands:
  build: "npm run build"
  lint: "npm run lint"
  unit_test: "npm test"
human_authorities:
  product: alice
  engineering_constitution: alice
  production_release: bob
  final_acceptance: alice
```

- `commands` are the exact shell commands the AI developer subagents will
  run to build, lint and test your project. If your project has no build
  step, leave that entry as `null` — it's fine.
- `human_authorities` are not roles for the AI to fill; they are the real
  names of the people who have final say at each of the framework's human
  gates (see "Runtime flow" below): who can change product scope, who can
  change the Engineering Constitution itself, who can authorize a
  production release, and who signs off on final acceptance. On a small
  project this can be the same name four times. The framework will name
  these people whenever it needs to ask a human for a decision.

**`.ai-team/sources/source-registry.yaml`** — one entry per document that
actually defines what you're building (requirements, specs, business
rules...). A commented example is at the top of the file; concretely, if
you drop a file at `docs/product/requirements.md`, register it like this:

```yaml
sources:
  - id: requirements-v1
    type: human_construction_material
    path: docs/product/requirements.md
    authority: human
    scope: project
    version: "1.0"
    status: active
    owner: product
```

Any product document you don't register here is invisible to the
framework: the AI agents only treat as authoritative the sources explicitly
listed.

Then check what, if anything, is still missing:

```bash
python scripts/ai-team/validate.py
```

This only ever reports on the two files above (and, later, on the Work
Units you create) — it does not ask you to touch the Constitution defaults.

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

If Cursor suddenly stops being able to run *any* shell command right after
you open the project, check the Requirements section above first: the
`beforeShellExecution` hook fails closed by design (see
`.cursor/hooks.json`), so a Python interpreter that doesn't match the exact
command name written there blocks commands instead of silently skipping
the check.

See `docs/SECURITY_MODEL.md`.

## Going further

- Full checklist before running on a real project: `docs/ADOPTER_CHECKLIST.md`.
- Step-by-step operator reference (also available in French): `docs/OPERATOR_GUIDE.fr.md`.
- Architecture, state machine and review pipeline: `docs/ARCHITECTURE.md`.
- What Cursor governance controls do and don't cover: `docs/SECURITY_MODEL.md`.
- Where each part of this repository maps back to the base design document: `docs/SOURCE_MAPPING.md`.

## License

MIT. See `LICENSE`.
