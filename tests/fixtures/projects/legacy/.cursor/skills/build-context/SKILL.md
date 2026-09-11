---
name: build-context
description: Assemble the minimum sufficient, traceable Context Package for a Work Unit, preserving provenance and allowing targeted context requests.
disable-model-invocation: false
icon: book-open
color: cyan
---
# Build Context Package

Apply the context hierarchy:

- L0 Constitution — only policies relevant to the role/Work Unit
- L1 Project — project scope, architecture and constraints
- L2 Relevant zone — requirements, contracts and decisions for the affected capability/components
- L3 Work Unit — objective, expected behavior, acceptance criteria, dependencies, files/symbols/tests

Do not dump the entire repository or every document when narrower context is sufficient.

Create/update a Context Package object containing each item's source/provenance and reason for inclusion.

Required machine fields (schema):

- `required_contracts` — shared contract paths the Work Unit depends on
- `completeness_status` — `complete` only when every required contract is present as an item `source` and `open_context_requests` is empty
- `missing_inputs` — list of still-missing contract paths or open requests
- `source_sha256` — hash of the package file once assembled (`sha256:…`)

If a required shared contract is absent, set `completeness_status: incomplete`, record it under `missing_inputs` / `open_context_requests`, and do **not** claim the package is ready for `implement-work-unit`. The orchestrator refuses dispatch while the package is incomplete.

If required information is absent, emit `CONTEXT_REQUEST` or `CLARIFICATION_REQUEST`; do not fill the gap by guesswork.
