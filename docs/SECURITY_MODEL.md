# Security model

## Governance controls in this repository

- Cursor subagent `readonly` restrictions for roles that must not modify code;
- Cursor project rules;
- Cursor hooks that log activity and block obvious hazardous commands;
- Cursor `permissions.json` guidance for Auto-review / allowlists;
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

The hooks and permissions guidance require human approval for or block:

- direct pushes to `main`, `master`, `trunk`;
- destructive Git history changes;
- destructive filesystem commands;
- production database mutations;
- production Kubernetes / Terraform / cloud mutations;
- secret and credential manipulation;
- permission/IAM changes;
- production deployment commands.

Adapt these patterns to your actual stack.
