# Using the framework with Cursor CLI

*[Lire en français](TERMINAL_GUIDE.fr.md)*

The framework supports two equivalent execution interfaces:

- the Cursor graphical interface;
- the interactive Cursor CLI started with `agent`.

Both modes share the same Constitution, Work Units, state, evidence,
decisions, rules, Skills, subagents and hooks. They may be used alternately
on one project, but must not write concurrently to the same Git checkout.

## Shared and mode-specific files

| Element | Cursor UI | Cursor CLI |
| --- | --- | --- |
| `.ai-team/` | shared | shared |
| `AGENTS.md` and `.cursor/rules/` | shared | shared |
| `.cursor/skills/` and `.cursor/agents/` | shared | shared |
| `.cursor/hooks.json` | shared | shared |
| Execution permissions | `.cursor/permissions.json` | `.cursor/cli.json` |

Keep both permission files. `.cursor/permissions.json` preserves UI behavior;
`.cursor/cli.json` configures the CLI separately. The mechanical blocks in
`.cursor/hooks/guard_shell.py` remain common defense in depth.

## 1. Prepare the CLI

Install Cursor CLI according to its official documentation, then verify it:

```bash
agent --version
```

Always start it from the installed project, not the framework repository:

```bash
cd /path/to/your/project
agent --workspace "$PWD"
```

Use interactive mode for governed cycles that may require approval or a human
decision. Headless/print mode is appropriate for pre-authorized noninteractive
checks, not full orchestration.

## 2. CLI permissions

Cursor accepts only `permissions.allow` and `permissions.deny` in the project
file `.cursor/cli.json`. Approval mode and notifications are global settings:
configure them with `/config` or in `~/.cursor/cli-config.json`, never in the
project file.

For the initial smoke test, select **Allowlist** and enable notifications in
`/config`. After subagent approval routing is validated, use **Auto-review**
for daily work with `/auto-review`: explicit permissions and sandboxing reduce
interruptions while ambiguous operations may still request approval. Do not
use Run Everything for the governed Orchestrator.

The shipped project file pre-authorizes repository reads except common
secrets, project writes except governance control files, read-only Git
commands, and the framework's validation/status/diagnostic/Definition-of-Done
scripts.

Build, lint and test commands are stack-specific. After the smoke test, add
their exact forms to `.cursor/cli.json` after completing
`.ai-team/project-profile.yaml`. In Allowlist mode, every unlisted command asks
for approval. In Auto-review mode, it goes through the sandbox and, when
needed, the classifier or human approval. A `deny` rule is a hard refusal, so
reserve it for secrets, the Constitution and explicitly hazardous operations.

## 3. Conservative first CLI cycle

Before the first CLI cycle, temporarily reduce and version these project
Constitution limits:

```yaml
# .ai-team/constitution/10-project-strategy.yaml
wip_limits:
  max_active_work_units: 1
  max_concurrent_code_writers: 1
```

```yaml
# .ai-team/constitution/60-staffing-policy.yaml
defaults:
  maximum_active_role_instances: 3
  maximum_code_writers: 1
```

Make the change before compiling a cycle; never modify the Constitution during
an active cycle. Increase the limits only after the smoke test below passes.

## 4. Run the workflow

In Cursor CLI:

```text
/compile-project

Compile the project from @docs/product/. Do not implement product code — stop
after producing the execution plan for my approval.
```

In a second terminal:

```bash
python scripts/ai-team/status.py
python scripts/ai-team/record_gate.py G1 approved --by YOUR_NAME --note "Execution plan approved"
```

Then in Cursor CLI:

```text
/orchestrator
```

You may invoke the Skill as a persistent Custom Mode from the `/` menu with
`Alt+Enter` or `Option+Enter`. Keep a second terminal open for `status.py` and
`diagnose.py`; a human gate decision must be recorded, not left only in chat.

## 5. Required subagent approval smoke test

Run this on a test branch with a disposable Work Unit:

1. verify that `agent --version` works;
2. start `agent --workspace "$PWD"`;
3. open `/config`, select Allowlist, and enable notifications;
4. verify that `.cursor/cli.json` exists and does not pre-authorize
   `Shell(whoami)`;
5. invoke `/orchestrator` with a READY Work Unit that needs no product edit;
6. ask the subagent to run exactly the harmless command `whoami`;
7. verify that the request appears in the parent terminal and a notification is
   visible;
8. deny it once and verify that a `BLOCKER` or `CLARIFICATION_REQUEST` is
   written before stopping;
9. retry, approve it, and verify that the subagent resumes and produces a
   handoff;
10. verify `.ai-team/logs/cursor-events.jsonl` contains `subagentStart`,
   `beforeShellExecution`, `afterShellExecution`, and `subagentStop`;
11. run `python scripts/ai-team/diagnose.py` and confirm there is no silent
    stall.

Do not enable concurrent Work Units or writers until all eleven observations
pass with the actual Cursor CLI version in use.

## 6. Switch between UI and CLI

Before switching modes, let the current agent finish or stop it explicitly,
resolve pending approvals, run `status.py` and `diagnose.py`, inspect
`git status`, and record the necessary handoff or BLOCKER. Only then open the
other interface on the same checkout.

For truly concurrent writers, use separate worktrees. Cursor CLI accepts
`agent --worktree WU-XXX`, but the Orchestrator must remain the sole authority
allocating Work Units and collecting results.

## 7. Security boundary

The terminal does not create a security boundary between the agent and your
system account. Keep protected branches, required CI, CODEOWNERS, secrets and
production credentials outside the model. See `SECURITY_MODEL.md`.
