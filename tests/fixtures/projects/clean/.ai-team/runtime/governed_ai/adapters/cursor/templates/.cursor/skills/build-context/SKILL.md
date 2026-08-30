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

If required information is absent, emit `CONTEXT_REQUEST` or `CLARIFICATION_REQUEST`; do not fill the gap by guesswork.
