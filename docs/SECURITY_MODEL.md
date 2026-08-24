# Security model

## Governance controls in this repository

- Cursor subagent `readonly` restrictions for roles that must not modify code;
- Cursor project rules;
- Cursor hooks that log activity and block obvious hazardous commands;
- Cursor `permissions.json` guidance for Auto-review / allowlists;
- Cursor CLI `.cursor/cli.json` allow/deny tokens and interactive approval mode;
- branch and release policy encoded in the Constitution.

## Controls that must remain external

This framework intentionally does **not** pretend that prompts are a security boundary.

Use your Git / CI / cloud platform to enforce:

- protected default branch;
- required status checks;
- CODEOWNERS or equivalent reviewer ownership;
- mandatory PR review for sensitive zones;
- deployment environment protection;
- production credentials unavailable to ordinary developer agents;
- secret manager rather than repository secrets;
- audited cloud/IAM roles;
- immutable or append-only deployment logs where appropriate.

## Default blocked command classes

Two different mechanisms are involved here, with two different strengths
of guarantee. Do not treat them as equivalent.

**Mechanically blocked** — matched by regex in `.cursor/hooks/guard_shell.py`
and denied *before execution*, regardless of what the agent intends
(`failClosed: true`, see "Troubleshooting" below):

- direct pushes to `main`, `master`, `trunk`;
- force push and `git reset --hard`;
- `rm -rf /` (and equivalents matching that exact pattern);
- `kubectl apply/delete/patch/replace/scale/rollout`;
- `terraform apply/destroy`;
- commands combining "prod"/"production" with deploy/migrate/delete/drop/truncate;
- `DROP DATABASE`, `DROP TABLE`, `TRUNCATE TABLE`.

**Behavioral guidance only in the UI** — listed in `.cursor/permissions.json` →
`autoRun.block_instructions` as plain-language instructions the agent is
expected to follow, but *not* matched by any hook pattern. Nothing stops
the agent mechanically if it disregards this guidance:

- secret and credential manipulation;
- permission/IAM changes;
- other destructive filesystem commands beyond the exact `rm -rf /` pattern above;
- adding a new dependency not already declared in the project manifest;
- starting a server bound to a non-local interface.

If your threat model requires secrets, IAM and credential changes to be
mechanically unblockable rather than merely discouraged, add matching
patterns to `guard_shell.py` yourself, or — better — enforce this outside
the model entirely (see "Controls that must remain external" above):
Cursor rules, hooks, `permissions.json` and `cli.json` are governance controls,
not a complete security boundary, and this is exactly the kind of gap that
external enforcement is meant to close.

For Cursor CLI, `.cursor/cli.json` adds mechanical `deny` tokens for the
framework's sensitive files and several hazardous command patterns. A CLI
`deny` is a hard refusal; an operation absent from both `allow` and `deny`
instead reaches the interactive approval flow. The shared `guard_shell.py`
hook remains defense in depth for both interfaces. Keep both permission files:
they serve different clients.

Adapt these patterns to your actual stack.

## Troubleshooting: a fail-closed hook has no effect if it can't run

`.cursor/hooks.json` sets `failClosed: true` on `guard_shell.py`, so the
default is to deny a shell command if the hook itself errors out — this is
intentional and correct: a broken hook must not silently stop protecting
you. The practical consequence is that every entry in `.cursor/hooks.json`
invokes `python` literally; if that exact command name isn't on PATH on
your machine (common on macOS and some Linux distributions, which may only
have `python3`), Cursor will be unable to run *any* shell command in this
project, not just the ones the hook is meant to block. See the
Requirements section in `README.md` for how to check and fix this.
