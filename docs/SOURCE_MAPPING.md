# Design-source mapping

This implementation follows the supplied design document's major concepts:

| Framework area | Design concept |
|---|---|
| `.ai-team/constitution/00-authority.yaml` | Human authority, source truth, change policy |
| `definition-of-ready.yaml` | Definition of Ready |
| `docs/product/*/` subfolders | Annexe A — construction-material checklist |
| `.cursor/skills/propose-profile/` | Onboarding convenience (not in the source document): proposes, never decides, project-profile.yaml / source-registry.yaml values from detected repository signals |
| `10-project-strategy.yaml` + `15-risk-strategy.yaml` | Project Strategy / Project State / risk-driven controls |
| `20-decomposition-strategy.yaml` | Work Unit + Decomposition Strategy |
| `30-context-strategy.yaml` | Context Strategy / Context Manager |
| `.cursor/skills/compile-project/` | Project Compiler |
| `.cursor/skills/orchestrator/` | Orchestrator / Control Plane |
| `.cursor/agents/` | Specialized roles |
| `60-staffing-policy.yaml` | Dynamic staffing |
| `70-permissions-policy.yaml` | Skills, permissions, least privilege |
| `80-communication-policy.yaml` | Structured messages |
| `40-test-strategy.yaml` | Test Strategy / evidence |
| `.cursor/agents/code-reviewer.md` | Review |
| `.cursor/BUGBOT.md` | Agent Review / Bugbot layer (pull-request-level review) |
| `.cursor/agents/auditor.md` + `50-audit-strategy.yaml` | Independent audit |
| `definition-of-done.yaml` | Definition of Done |
| `90-gates-and-autonomy.yaml` | G0-G4 + autonomy levels |
| `.ai-team/acceptance/` | Human acceptance / defects / remediation |

The source document intentionally left some parameters open. This repository chooses explicit reference defaults for WIP, worker counts, activation thresholds, autonomy default, and a baseline permission matrix. Those values are tagged as implementation defaults and are meant to be versioned when changed.
