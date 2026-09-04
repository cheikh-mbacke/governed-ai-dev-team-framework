---
name: assess-adoption
description: Assess a candidate repository for Governed AI Team adoption before installation, without modifying the target. Use when the human invokes /assess-adoption with a target path.
disable-model-invocation: true
argument-hint: "<target-path> [--resolutions <file>] [--json] [--report-file <file>]"
icon: clipboard-check
color: blue
---
# Assess Adoption

Run the framework's pre-installation adoption assessment. This is a
fabrication/operator command, not an installed-client lifecycle command.

## Safety boundary

- Treat the first argument as the candidate repository root and resolve it before
  running anything.
- Remain read-only with respect to the candidate repository.
- Do not install the framework, delete or remap conflicts, edit a resolutions
  file, or invoke `/reconcile-project` as part of this command.
- A report file may be written only when the human explicitly supplies
  `--report-file`. Warn before continuing if that path is inside the candidate
  repository.
- Apply `--resolutions` only from an existing human-provided JSON file. Never
  invent a resolution, a waiver, or a `waiver_authorization_id`.

## Execute

1. Confirm that `tools/assess.py` exists in the current framework source checkout.
2. If no target path was supplied, ask for exactly that path and stop.
3. Run:

   ```bash
   python tools/assess.py --target <target-path>
   ```

4. Forward only the optional flags explicitly supplied by the human:
   `--resolutions`, `--json`, and `--report-file`.
5. Interpret the exit code as part of the assessment protocol:
   - `0`: `go` or `go_with_backlog`;
   - `2`: `no_go`, not a tool failure;
   - `1`: execution or input error.

## Report

Return the verdict, blocking findings, warnings/backlog, and the next human
decision required. Distinguish these stages explicitly:

```text
/assess-adoption (read-only, before install)
  -> human adoption decision
  -> install
  -> /reconcile-project (establish coherent baseline)
  -> /compile-project
```

Never describe `go_with_backlog` as permission to compile. On a brownfield
project, baseline findings remain for `/reconcile-project` after installation.
