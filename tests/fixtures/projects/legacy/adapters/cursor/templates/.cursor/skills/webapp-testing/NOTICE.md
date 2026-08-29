SKILL.md in this directory is adapted (setup note added, see the top of
the file; instructional content otherwise unmodified) from:

  https://github.com/anthropics/skills (path: webapp-testing/)
  Copyright Anthropic, PBC
  Licensed under the Apache License, Version 2.0 (see LICENSE.txt)

scripts/ and examples/ from the upstream skill are NOT included here —
see the setup note at the top of SKILL.md for why and how to fetch them.
This is a deliberate difference from frontend-design's vendoring (which is
fully self-contained): those scripts are large, meant to be run as black
boxes rather than read, and are best kept in sync with upstream directly
rather than copied.

Wired into this framework's governance: referenced from
.cursor/agents/frontend-developer.md, .cursor/agents/qa-test.md and
.cursor/agents/code-reviewer.md as the tool for producing real evidence
(screenshots, DOM state) for .ai-team/constitution/35-ui-ux-strategy.yaml
sections 6 (required states) and 7 (accessibility) — not a suggestion, a
prerequisite for those sections' verification.
