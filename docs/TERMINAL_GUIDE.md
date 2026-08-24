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

For the initial smoke test, select **Allowlist** in `/config`. Enable
notifications when the platform supports them; on some Windows Cursor CLI
builds notifications are `unsupported` — that is not a smoke-test failure.
After subagent approval routing is validated, use **Auto-review** for daily
work with `/auto-review`: explicit permissions and sandboxing reduce
interruptions while ambiguous operations may still request approval. Do not
use Run Everything for the governed Orchestrator.

Project `.cursor/cli.json` may only contain `permissions.allow` /
`permissions.deny`. Absence of `approvalMode` or `notifications` in that file
is expected and must not be treated as a failure.

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

This smoke test validates **CLI Allowlist routing** from a subagent to the
parent terminal. It is not a product Work Unit cycle.

### Where to run it

- Run it **only** with interactive Cursor CLI: `agent --workspace "$PWD"`.
- Do **not** run it from the Cursor UI Agent chat (Task / IDE subagent tools).
  UI permissions (`.cursor/permissions.json`) can execute `whoami` without the
  CLI Allowlist prompt, so a successful IDE run does **not** validate this path.

### Automated environment preflight (do this first)

Separate environment failures from Allowlist failures. Before starting
`agent`, use whichever Python 3 command works on the host:

```bash
python scripts/ai-team/preflight.py
```

The dependency-free preflight checks the committed hook configuration, runs
`guard_shell.py` through the same portable runner Cursor uses, verifies the
project CLI permissions, and reports the platform capability profile. It does
not read Cursor's global settings or simulate a human approval; those two
items remain clearly marked `MANUAL`.

Do not edit `.cursor/hooks.json` to swap `python` and `python3`. The committed
`.cursor/hooks/run_hook.cmd` selects `python3` / `python` on POSIX and
`python3` / `python` / `py -3` on Windows, and preserves the hook's first exit
code. A missing interpreter or fail-closed hook is reported as `BLOCKED`
before the authorization scenario begins.

### Platform choice for the subagent

| Goal | Subagent | Notes |
| --- | --- | --- |
| Allowlist prompt / deny / allow-once | `auth-smoke` | Cross-platform routing probe with `readonly: false`; it does not validate the real Architect role |
| `workspace_readonly` sandbox path | `architect` | Separate integration test with `readonly: true`; `SKIP` on Windows native, required under WSL/Linux |

Do not weaken `architect` to pass the Allowlist smoke test.

### Procedure

1. Verify `agent --version`.
2. From the project root, start `agent --workspace "$PWD"`.
3. Open `/config`, set approval mode to **Allowlist**. Confirm
   `Shell(whoami)` is **not** in the global or project allowlist. Notifications
   may be `unsupported` on some Windows builds — ignore that for pass/fail.
4. Confirm project `.cursor/cli.json` has `permissions.allow` /
   `permissions.deny`, does **not** contain `approvalMode` /
   `notifications`, and does not allow `Shell(whoami)`.
5. Note the current end of `.ai-team/logs/cursor-events.jsonl` (if present).
6. Ask the CLI agent to launch **`auth-smoke` in the foreground** with this
   mission only: run exactly `whoami`; report stdout or an authorization
   refusal; do not edit files; do not substitute another command.
7. Confirm a parent-terminal prompt appears (`Not in allowlist: whoami` or
   equivalent). **Skip / deny** once (`n` or Esc). Do not add `Shell(whoami)`
   to the allowlist; do not choose Run Everything.
8. Paste the **same** prompt again. When the prompt reappears, choose
   **Run once** (`y`). Confirm `whoami` stdout and a normal subagent handoff.
9. Inspect only new lines in `.ai-team/logs/cursor-events.jsonl` for
   `subagentStart`, `beforeShellExecution`, `afterShellExecution` (for the
   allowed attempt), and `subagentStop`. An `afterShellExecution` is not
   required for the denied attempt.
10. Run `git status --short`. No unexpected repo changes beyond the ignored
    log file.
11. Run `python scripts/ai-team/diagnose.py` (or your working Python command)
    and confirm there is no silent stall.

### Diagnostic order

1. Does `preflight.py` report `PASS` for `hooks_config`, `guard_hook`, and
   `project_cli`?
2. Is the Allowlist prompt visible in the **CLI** parent terminal?
3. Only then: Skip → same prompt → Run once → check hooks.

A fail-closed hook error or a missing sandbox is an **environment** failure,
not an Allowlist pass or fail.

Do not raise WIP / concurrent writers until this smoke test passes on the
Cursor CLI version you actually use.

Required integration check for full CLI support: under WSL/Linux, repeat a
shell attempt with `architect` to confirm `workspace_readonly` works on that
host. Record it independently from the `auth-smoke` result. On Windows native,
report this check as `SKIP — Cursor workspace_readonly unavailable`, never as
an Allowlist failure or a pass.

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
