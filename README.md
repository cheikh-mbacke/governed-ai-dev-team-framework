# Governed AI Development Team Framework

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
- Engineering Constitution in `.ai-team/constitution/`
- JSON Schemas for all core state objects in `.ai-team/schemas/`
- Ready-to-use templates in `.ai-team/templates/`
- Runtime directories for Work Units, decisions, evidence, findings, audit, release and acceptance
- Validation and status tooling in `scripts/ai-team/`
- Cross-platform installer in `tools/install.py`
- A complete walkthrough in `examples/project-a/`

## Install into an existing project

Clone this framework anywhere, then run:

```bash
python tools/install.py \
  --target /path/to/your/project \
  --project-id project-a \
  --project-name "Project A"
```

The installer copies the framework into the target repository without overwriting existing files unless `--force` is used.

Then, from the target repository:

```bash
python scripts/ai-team/validate.py
python scripts/ai-team/status.py
# Human gate decisions can be recorded explicitly, e.g.:
python scripts/ai-team/record_gate.py G1 approved --by YOUR_NAME --note "Execution plan approved"
```

## First Cursor session

1. Put your human product material under `docs/product/`.
2. Register authoritative sources in `.ai-team/sources/source-registry.yaml`.
3. Open the repository in Cursor.
4. Explicitly invoke:

```text
/compile-project
```

5. Inspect the generated execution model.
6. Approve gate **G1** only when satisfied.
7. Start the orchestrator as a Custom Mode or explicitly invoke:

```text
/orchestrator
```

The orchestrator then activates specialist subagents only when a Work Unit and policy require them.

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

## Project-specific values that adopters must fill

The framework itself is intentionally fully specified. A project adopter still needs to provide the project-specific matter that no generic framework can know:

- project identity and repository metadata;
- authoritative product sources;
- product architecture and constraints;
- domain-specific risk overrides;
- actual test/build/lint commands;
- repository path map;
- production environments and deployment mechanism;
- organization-specific identities for human approvers.

The installer creates these locations and the validation tooling tells you exactly what remains incomplete.

## License

MIT. See `LICENSE`.
