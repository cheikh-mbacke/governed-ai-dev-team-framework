# Document 22 — Conformité : réconciliation pré-compilation

**Statut** : version 1.0 — critères d’acceptation du Document 21.

## Scénarios obligatoires

### REC-AC-001 — Commande livrée

Après installation, la skill `/reconcile-project`, le script
`scripts/ai-team/reconcile_project.py` et le schéma de rapport sont présents.

### REC-AC-002 — Baseline absente

`reconcile_project.py check` retourne un code non nul et demande
`/reconcile-project` si aucun rapport n’existe.

### REC-AC-003 — Matière humaine insuffisante

Une dimension manquante ou ambiguë, ou une dimension suffisante sans référence
autoritaire, interdit la finalisation.

### REC-AC-004 — Brownfield sans inventaire

Quand du code applicatif est détecté, un inventaire as-built vide interdit la
finalisation.

### REC-AC-005 — Convergence non terminée

Une décision ouverte, un item non `completed`/`waived`, un conflit bloquant ou une
vérification en échec interdit l’état `ready`.

### REC-AC-006 — Action sensible sans approbation

Une action `migrate`, `rewrite`, `isolate` ou `delete`, ainsi que toute résolution
d’un item `conflicting` ou `undetermined`, sans `human_approval_ref` est rejetée.

### REC-AC-007 — Empreinte déterministe

Modifier un fichier géré par le framework ou le rapport lui-même ne change pas
l’empreinte project-owned ; modifier un fichier produit la change.

### REC-AC-008 — Dérive après finalisation

Après une finalisation réussie, toute modification project-owned fait échouer
`check` avec une baseline obsolète.

### REC-AC-009 — Verrou de compilation

Le contrat et la skill `/compile-project` exigent le contrôle machine de la
réconciliation et imposent l’arrêt sur code non nul.

### REC-AC-010 — Séparation des responsabilités

`/reconcile-project` s’arrête après la baseline ; elle ne crée ni Work Unit ni plan
d’exécution. `/compile-project` reste planning-only et ne corrige pas silencieusement
les écarts as-built.

## Preuves minimales

| Critères | Preuve |
|---|---|
| REC-AC-001, 002 | Test d’installation et exécution CLI sur cible isolée |
| REC-AC-003 à 008 | Tests unitaires du domaine de réconciliation |
| REC-AC-009 | Test de contrat bundle et contrôle du contenu de skill |
| REC-AC-010 | Parité sémantique procédure ↔ adaptateur et revue documentaire |

## Références

- Document 21 — Réconciliation pré-compilation
- Document 14 — Tests de conformité généraux
