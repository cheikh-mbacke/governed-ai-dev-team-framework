# Human product material

Put your authoritative product documents under the subfolders below, or
register files from wherever they actually live in
`.ai-team/sources/source-registry.yaml` — nothing has to physically live
here. The subfolders are an optional organizational aid, not a required
format: use as many or as few as your project needs, and put more than one
topic in a single file if that's simpler.

The seven categories below come from asking one question exhaustively
against the framework's base design document: *what must the human
actually produce for the AI team to build the right thing?* They cover
every item on that document's construction-material checklist (Annexe A)
with nothing left out and nothing added — see `docs/SOURCE_MAPPING.md`.

- `vision-and-scope/` — the result you're after, and what's explicitly out of scope.
- `users-and-rules/` — who uses the system, their journeys, and the business rules/invariants that govern behavior.
- `requirements/` — functional and non-functional requirements, and any specification detail needed to avoid ambiguity.
- `acceptance-criteria/` — the observable results that make a piece of work count as done.
- `architecture-and-constraints/` — architecture, interface contracts, and imposed technical/operational constraints (stack, versions, environments).
- `security-and-compliance/` — access control, data, secrets, audit and regulatory requirements.
- `references/` — reference data, examples, mockups or expected proof artifacts.
