---
name: audit-release
description: Coordinate an independent release-level audit using the Auditor subagent and the eight-pass Audit Strategy, then write a conformity report without remediation.
disable-model-invocation: false
icon: shield
color: red
---
# Audit Release

Delegate the measurement to the `auditor` subagent with a clean, sufficient context containing authoritative intent, repository revision, evidence and runtime observations.

Do not prime the Auditor with conclusions such as "everything passed".

Write the audit report under `.ai-team/audits/` and findings under `.ai-team/findings/`.

Any remediation must be created as a separate Work Unit and then re-verified and re-audited.
