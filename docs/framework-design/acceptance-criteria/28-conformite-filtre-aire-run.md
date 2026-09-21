# Document 28 — Conformité : filtre d’aire sur RunAuthorizationGrant

**Statut** : version 1.0 — critères d’acceptation du Document 27.

## Scénarios obligatoires

### AREA-AC-001 — Schéma

Le schéma `run-authorization-grant.schema.json` admet `allowed_areas` (tableau
non vide de valeurs enum hors `unknown`) et
`area_filter_dependency_policy` (`skip_blocked` | `stop_on_cross_area_dependency`).
L’absence des deux champs reste valide.

### AREA-AC-002 — Émission cohérente

`IssueRunAuthorizationGrant` avec `allowed_areas: [backend]` et une Work Unit
`zone.area: frontend` dans `work_unit_ids` est rejeté.

### AREA-AC-003 — Émission `unknown`

`IssueRunAuthorizationGrant` avec filtre actif et une Work Unit
`zone.area: unknown` est rejeté.

### AREA-AC-004 — OpenRun hors aire

`OpenRun` dont le payload inclut une Work Unit couverte par `work_unit_ids`
mais hors `allowed_areas` est refusé (`UNAUTHORIZED`).

### AREA-AC-005 — Dispatch filtré

Sur un Run ouvert avec `allowed_areas: [backend]`, une Work Unit frontend
présente dans le Run n’est jamais dispatchée ; la raison observée est
`area_filter_mismatch`.

### AREA-AC-006 — Dépendance `skip_blocked`

Avec politique `skip_blocked`, WU-B (backend) dépend de WU-F (frontend hors
filtre) : WU-B n’est pas dispatchée ; une autre WU backend indépendante peut
l’être ; le Run ne s’arrête pas uniquement pour cette dépendance tant qu’il
reste du travail éligible.

### AREA-AC-007 — Dépendance `stop_on_cross_area_dependency`

Avec cette politique, dès que la seule WU restante éligible est bloquée
uniquement par une dépendance hors filtre, le Run se termine avec
`stop_condition: cross_area_dependency`.

### AREA-AC-008 — Compatibilité rétrograde

Un grant sans `allowed_areas` se comporte comme avant : toute Work Unit de
`work_unit_ids` reste éligible côté aire.

### AREA-AC-009 — `fullstack` non implicite

`allowed_areas: [backend]` n’autorise pas une Work Unit `fullstack`.

## Preuves minimales

| Critères | Preuve |
|---|---|
| AREA-AC-001 | Validation schéma / fixture grant |
| AREA-AC-002, 003 | Tests unitaires `IssueRunAuthorizationGrant` |
| AREA-AC-004 | Tests unitaires autorisation `OpenRun` |
| AREA-AC-005 à 007, 009 | Tests orchestrator tick / dispatch |
| AREA-AC-008 | Test de non-régression grant legacy |

## Références

- Document 27 — Filtre d’aire sur RunAuthorizationGrant
- Document 14 — Tests de conformité généraux
