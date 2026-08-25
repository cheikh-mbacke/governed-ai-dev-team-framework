# Operator guide

*[Lire en français](OPERATOR_GUIDE.fr.md)*

This guide details each step. For the fast path, see the Quickstart in
`README.md` — the two correspond; this guide just gives more context on
each step.

## 1. Install the framework

Use `tools/install.py`. The framework is copied into the project repo
without assuming any particular tech stack. The framework's `examples/`
folder is never copied.

## 2. Fill in the construction material

Place human documents under `docs/product/`, then fill in
`.ai-team/sources/source-registry.yaml`. A commented example is already
present at the top of the file.

A source must state:

- its stable identifier;
- its path or URI;
- its authority;
- its scope;
- its version;
- its status.

## 3. Complete the project profile

`.ai-team/project-profile.yaml` holds the project's technical commands:
build, lint, tests, source/test/doc paths, environments and release
rules. A commented example is at the top of the file. It's the only
other file that's genuinely empty — everything else in the Constitution
is already a working default.

## 4. Open the project in Cursor

Use either Cursor UI or the interactive Cursor CLI on the **installed project**
(not this framework repository). Trust the workspace in the UI; in a terminal,
run `agent --workspace "$PWD"` from the project root. Both modes discover
`.cursor/rules/`, `.cursor/agents/`, `.cursor/skills/` and
`.cursor/hooks.json`, and share `.ai-team/`. Do not let them write to the same
checkout concurrently. See `TERMINAL_GUIDE.md` for CLI configuration and its
smoke test (CLI Allowlist via `auth-smoke`, not the UI Agent chat).

## 5. Compile before implementing

In Cursor UI or CLI, explicitly invoke the Skill (it is not auto-triggered):

```text
/compile-project

Compile the project from @docs/product/. Do not implement any product
code — stop after producing the execution plan for my approval.
```

The Compiler must produce or update:

- `.ai-team/state/project-state.yaml`;
- `.ai-team/work-units/*.yaml`;
- dependencies;
- risk classes;
- required verification;
- context plan;
- initial staffing;
- missing decisions.

No product code is touched during this step.

## 6. Approve G1

The human inspects the plan. They approve, request changes, or reject.
An approval is recorded under `.ai-team/decisions/` and in the Project
State.

## 7. Start the orchestrator

Use the `orchestrator` Skill as a Custom Mode, or invoke it explicitly.
The Control Plane only selects Work Units that are ready, within WIP
limits.

## 8. Execution

For each Work Unit:

1. build a minimal Context Package;
2. choose staffing;
3. delegate to the appropriate Developer;
4. run developer checks and inspect the diff;
5. create a coherent commit on the Work Unit branch with its ID in the message;
6. hand the exact SHA to QA and Reviewer;
7. trigger QA;
8. trigger Reviewer;
9. trigger Security if policy requires it;
10. trigger Auditor if policy requires it;
11. produce the human acceptance package;
12. close only once the Definition of Done is satisfied.

The Developer does not need separate human confirmation for each coherent commit
on an isolated branch. It must stop before a protected-branch commit, merge,
unauthorized push, or history rewrite. Remediation creates a new commit and the
affected checks run again on the new SHA. A WIP commit may preserve interrupted
work but cannot enter QA as a verified candidate.

## 9. If it looks stuck

**First, before any script**: in the UI, scroll up and check for a pending
"Run"/"Approve" button; in the CLI, check the parent terminal for a pending
approval request. This is the most
common and most invisible cause — a command that wasn't auto-approved
(starting the local server, running Playwright, installing a dependency)
suspends the agent *before* it can write anything at all. Nothing this
framework records can detect this state, because no event is written
until the command has actually run. If you keep hitting this for a given
command type, add a matching rule under `.cursor/permissions.json` →
`autoRun.allow_instructions` for the UI, or an exact permission token in
`.cursor/cli.json` for the CLI, instead of approving it every time.

If that's not it, before stopping and restarting — the only option when
you have nothing concrete to look at — run:

```bash
python scripts/ai-team/diagnose.py
```

This script answers, without modifying anything, three questions in
order:

1. **Is there an open `BLOCKER`/`CLARIFICATION_REQUEST`/`DECISION_REQUEST`
   event marked `requires_human: true`** under `.ai-team/events/`? If so,
   that's the real cause — resolve it, no need to restart anything.
2. **Which Work Units are "in flight"** (neither `ready` nor `done`)?
3. **When did the last recorded Cursor activity happen**
   (`.ai-team/logs/cursor-events.jsonl`)? If it's been a while and no
   event explains why, that's a genuine silent stall — not something you
   did wrong.

The Constitution now requires that an agent unable to continue write a
`BLOCKER` before stopping (`80-communication-policy.yaml` §
`never_stop_silently`) — if you still hit a stop with no trace at all,
that's a real gap worth reporting, not just "restart and hope". In this
specific case only, first ask the agent involved what it was doing right
before the session was cut — that gives a chance to get the reason
instead of losing it.

## 10. Missing decision

A missing product decision becomes a `DECISION_REQUEST`, never a
guess. Only dependent Work Units are blocked.

## 11. Release

A release candidate ties together a commit or set of commits,
migrations, evidence, reviews, open findings and a rollback plan. G3
protects production.

## 12. Acceptance

Agents prepare the scenarios. The human executes them and records PASS /
FAIL / PARTIAL. A failure produces a Defect and a remediation Work Unit.
