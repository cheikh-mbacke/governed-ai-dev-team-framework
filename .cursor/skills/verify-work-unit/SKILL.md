---
name: verify-work-unit
description: Evaluate whether a Work Unit has the required evidence, QA, review, audit and acceptance prerequisites for its current risk level and Definition of Done.
disable-model-invocation: false
icon: beaker
color: green
---
# Verify Work Unit

Read the Work Unit, Test Strategy, Definition of Done and evidence objects.

Check that required verification is not merely claimed but linked to concrete results and the evaluated code revision.

Report:
- satisfied checks;
- missing checks;
- failed checks;
- critical blockers/defects/findings;
- whether the Work Unit may transition to the next state.

Do not mark human acceptance complete unless an explicit human result exists.
