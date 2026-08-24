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
- Cursor CLI per-repository permissions in `.cursor/cli.json`
- Cursor Bugbot rules in `.cursor/BUGBOT.md`
- Engineering Constitution in `.ai-team/constitution/`
- JSON Schemas for all core state objects in `.ai-team/schemas/`
- Ready-to-use templates in `.ai-team/templates/`
- Runtime directories for Work Units, decisions, evidence, findings, audit, release and acceptance
- Validation and status tooling in `scripts/ai-team/`
- Cross-platform installer in `tools/install.py`
- An optional, non-installed reference example in `examples/project-a/`

## Requirements

- **Python 3.10 or later**, available on your PATH as `python3` (preferred)
  and/or `python`.
- Before installing, run `python3 --version`. If that command isn't found,
  try `python --version` instead.
  - Project hooks in `.cursor/hooks.json` invoke **`python3`** literally.
    On macOS and most Linux/WSL installs that is the correct default. If
    your machine only provides `python` (common on some Windows setups),
    open `.cursor/hooks.json` after install and replace every
    `"command": "python3 ...` with `"command": "python ...`. Cursor runs
    those strings as-is and will fail closed on shell commands if the
    name is missing from PATH.
  - For commands you type yourself in this guide, use whichever of
    `python3` / `python` works on your PATH.
- Cursor, either with the target project opened as a **trusted workspace** in
  the UI or through the interactive `agent` Cursor CLI (see step 3).
- Two Python packages: PyYAML and jsonschema. Install them once, from
  inside the cloned framework folder, before running `install.py`:

  ```bash
  pip install -r requirements.txt
  ```

  If `pip` isn't found, try `pip3` (same reasoning as `python`/`python3`
  above). On some Linux distributions, `pip` may refuse a global install
  with an "externally-managed-environment" error — in that case, either
  add `--user` (`pip install --user -r requirements.txt`) or create a
  virtual environment first: `python -m venv .venv`, then activate it
  (`source .venv/bin/activate` on macOS/Linux, `.venv\Scripts\activate` on
  Windows) before installing. Every script in this framework
  (`install.py`, `validate.py`, `status.py`, ...) checks for these
  packages itself and tells you to run this command if either is missing,
  instead of failing with a raw Python error.
- **Always type `python` (or `python3`) before a script's path** —
  `python scripts/ai-team/validate.py`, never just
  `scripts/ai-team/validate.py`. On Windows especially, typing a bare
  `.py` path can silently open the file in your editor instead of running
  it (Windows resolves `.py` through its own file association, which may
  well be Cursor itself), printing editor startup logs instead of a
  Python error — confusing if you don't know that's what happened.

## Quickstart

### 1. Get the framework and install it into your project

```bash
git clone https://github.com/cheikh-mbacke/governed-ai-dev-team-framework.git
cd governed-ai-dev-team-framework
```

Run the installer **from inside this cloned folder** — `tools/install.py`
is a path relative to it, not to your project or to wherever your terminal
happens to be. Replace `/path/to/your/project`, `your-project-id` and
`"Your Project Name"` below with your own project's actual values:

```bash
python tools/install.py --target /path/to/your/project --project-id your-project-id --project-name "Your Project Name"
```

Running from somewhere else instead? Give the full path to the script,
e.g. `python ~/governed-ai-dev-team-framework/tools/install.py ...`.

One line on purpose, so it pastes cleanly into any shell. If you split it
yourself, the line-continuation character differs by shell: `\` on
bash/zsh/Git Bash, `^` on `cmd.exe`, `` ` `` on PowerShell.

`install.py` never overwrites a file that already exists in the target
unless you pass `--force`, and never copies `examples/`.

Picking up a framework fix after you've already installed and started
working? Re-run the same command with `--update` instead of `--force`: it
overwrites governance files (agents, skills, rules, hooks, permissions,
Constitution, schemas, scripts) to the latest version, and leaves your
project data — `project-profile.yaml`, `source-registry.yaml`, Work
Units, state, decisions, events, evidence, everything you've written
under `docs/product/` — completely untouched. `--force` overwrites
everything, including that data; use `--update` instead unless you
specifically want a clean slate.

### 2. Fill in what only you know

Two files under `.ai-team/` are empty and need real values before you
compile anything. Everything else in the Constitution is already ready to
use — no external design document required to understand these two.

**`.ai-team/sources/source-registry.yaml`** — one entry per document that
defines what you're building. The installer already created seven category
subfolders under `docs/product/` — `vision-and-scope/`, `users-and-rules/`,
`requirements/`, `acceptance-criteria/`, `architecture-and-constraints/`,
`security-and-compliance/`, `references/` — each with a short README (see
`docs/product/README.md`). Using them is optional; one flat file works
just as well. A commented example is at the top of the registry file;
concretely, dropping a file at `docs/product/requirements/requirements.md`
gets registered like this:

```yaml
sources:
  - id: requirements-v1
    type: human_construction_material
    path: docs/product/requirements/requirements.md
    authority: human
    scope: requirements
    version: "1.0"
    status: active
    owner: product
```

An unregistered document is invisible to the framework: agents only treat
as authoritative the sources explicitly listed here.

**`.ai-team/project-profile.yaml`** — open it and replace the placeholder
values. A commented example is at the top; concretely, a filled profile
looks like this:

```yaml
project:
  id: checkout-service
  name: Checkout Service
communication:
  language: english
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

- `communication.language` is the language agents use when talking to you
  and when writing human-facing text (Work Unit titles, questions,
  explanations) — a language name or code, e.g. `français`, `español`,
  `fr`. It's free text, not an enum: nothing else in this framework
  changes language regardless of this setting — YAML keys, enum values
  like `status: ready`, file paths, commands and code always stay as
  defined.
- `commands` are the exact shell commands the developer subagents run to
  build, lint and test your project. No build step? Leave it `null`.
- `human_authorities` aren't roles for the AI — they're the real names of
  the people with final say at each human gate (see "Runtime flow" below):
  who can change product scope, who can change the Constitution itself,
  who authorizes a production release, who signs off on final acceptance.
  The same name four times is fine on a small project. The framework names
  these people whenever it needs a human decision.

Rather not fill these by hand? Once the project is open in Cursor (step 3),
invoke `/propose-profile` instead: it inspects your repository and
`docs/product/` for concrete signals already there — a `package.json`
script, a `Cargo.toml`, files you've dropped in the category folders — and
proposes values for both files above. It never writes anything until you
confirm, and never guesses your human approvers; it always asks directly.

Then check what's still missing:

```bash
python scripts/ai-team/validate.py
```

It checks these two files and prints one warning per gap — for example
`WARN Project command 'build' is not configured`, or
`WARN No authoritative product sources are registered`. Fix, rerun, repeat
until both are warning-free. (It starts reporting on Work Units too once
you create some in step 4 below — expected, not a problem with your
setup.) It never asks you to touch `.ai-team/constitution/` — that's
already complete.

### 3. Choose Cursor UI or Cursor CLI

In the UI, open **your project's folder** — the one you installed into at step
1, not the framework repository — and trust the workspace. If a `/` command
does not appear, close and reopen Cursor to force rules, agents, Skills and
hooks to be rediscovered.

In a terminal, start the interactive agent from that same project:

```bash
cd /path/to/your/project
agent --workspace "$PWD"
```

Both modes share the same governed state. Do not let them write to the same
checkout concurrently. The UI keeps its execution guidance in
`.cursor/permissions.json`; the CLI uses `.cursor/cli.json`. See
`docs/TERMINAL_GUIDE.md` for the conservative initial profile, subagent
approval smoke test and safe switching procedure.

### 4. Compile the project

In any regular Cursor Agent session, UI or CLI — there is nothing special to
select first — explicitly invoke the Skill. It is deliberately not
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

This prints a short, human-readable summary of what `/compile-project` just
produced: the current phase, the status of each gate (G0 through G4), how
many Work Units exist and their status, and any open decisions or defects.
It's a shortcut so you don't have to open every file under
`.ai-team/state/` and `.ai-team/work-units/` by hand — you're welcome to
read those directly instead if you prefer.

Read the proposed Work Units and staffing. When you're satisfied:

```bash
python scripts/ai-team/record_gate.py G1 approved --by YOUR_NAME --note "Execution plan approved"
```

### 6. Start the orchestrator

In the Cursor Agent, UI or CLI, type:

```text
/orchestrator
```

This runs one coordination pass: it looks at the Work Units you just
approved, starts the specialist subagents (developer, QA, reviewer...) for
whichever ones are ready, and stops. To keep it running for the rest of the
session instead of retyping `/orchestrator` after every step, use Cursor's
Custom Mode: open the chat's mode selector, create or select a Custom Mode
based on the `orchestrator` Skill, and chat in that mode — it keeps the
orchestrator's instructions active throughout.

Either way, it never starts every Work Unit and every subagent at once. It
respects the WIP (work-in-progress) limits below — by default, at most 3
Work Units active and at most 2 developer subagents writing code at the
same time — so if you approved 5 Work Units, only 2 or 3 start immediately
and the rest begin automatically as earlier ones finish or free up a slot.

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
command name written there (`python3` by default) blocks commands instead of
silently skipping the check.

See `docs/SECURITY_MODEL.md`.

## Going further

- Full checklist before running on a real project: `docs/ADOPTER_CHECKLIST.md`.
- Step-by-step operator reference (also available in French): `docs/OPERATOR_GUIDE.md`.
- Combined Cursor UI and CLI operation: `docs/TERMINAL_GUIDE.md`.
- Architecture, state machine and review pipeline: `docs/ARCHITECTURE.md`.
- What Cursor governance controls do and don't cover: `docs/SECURITY_MODEL.md`.
- Where each part of this repository maps back to the base design document: `docs/SOURCE_MAPPING.md`.

To verify the framework itself after a change:

```bash
python -m unittest discover -s tests -v
python scripts/ai-team/validate.py
```

## License

MIT. See `LICENSE`.
