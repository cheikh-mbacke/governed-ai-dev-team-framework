# Document 20 — Conformité : assessment d’adoption

**Statut** : version 1.2 — critères d’acceptation pour le Document 19. La CLI `tools/assess.py` et les tests `tests/distribution/test_assessment.py` fournissent la preuve automatisée des scénarios ADO-AC-001 à 011 (hors revue documentaire résiduelle).

## 1. Périmètre

Ces critères portent sur :

- le caractère non mutant de l’assessment ;
- le contenu minimal du rapport ;
- le verdict GO / NO-GO ;
- la distinction avec preflight / diagnose ;
- l’absence de mode hybride ;
- la catégorie `baseline` (matière humaine / inventaire as-built).

Ils ne portent pas sur le cycle G0–G4 post-install (Document 14), sauf pour exiger que la documentation adoptant décrive `/reconcile-project` **entre** install et G0/compile.

## 2. Scénarios obligatoires

### ADO-AC-001 — Cible sans framework

**Étant donné** un dépôt ordinateur sans `.ai-team/installation-record.json`  
**Quand** l’assessment est exécuté sur `--target`  
**Alors** il se termine avec un code de sortie documenté, produit un rapport, et l’arbre cible est octet-identique (hors fichier de rapport explicitement demandé hors cible ou sur stdout).

### ADO-AC-002 — Aucune mutation sur collision potentielle

**Étant donné** une cible avec `.cursor/cli.json` custom  
**Quand** l’assessment s’exécute  
**Alors** le fichier custom est inchangé et le rapport contient au moins un constat `artifact` le concernant.

### ADO-AC-003 — Verdict `no_go` si blocking non résolu

**Étant donné** au moins un constat `blocking` en `unresolved` ou `defer_blocks_adoption`  
**Quand** le rapport est finalisé  
**Alors** le verdict est `no_go`.

### ADO-AC-004 — Verdict `go` seulement sans blocking ouvert

**Étant donné** tous les constats `blocking` en `eliminate`, `remap` ou `waive` tracé  
**Quand** le rapport est finalisé  
**Alors** le verdict est `go` ou `go_with_backlog` (si des `warning` restent).

### ADO-AC-005 — Catégories présentes

**Étant donné** un assessment sur un brownfield représentatif (code métier + éventuellement `.cursor/` + `AGENTS.md`)  
**Quand** le rapport est produit  
**Alors** les catégories `engagement`, `authority`, `artifact`, `prerequisite`, `baseline` et `remodel` sont adressables (constat ou section explicite « néant »).

### ADO-AC-006 — Pas de mode hybride

**Étant donné** la sortie humaine et machine de l’assessment  
**Quand** un opérateur cherche une option « garder l’autorité concurrente sans résolution »  
**Alors** aucune option de ce type n’est proposée ; le seul report est `defer_blocks_adoption` / `no_go`.

### ADO-AC-007 — Séparation preflight / diagnose

**Étant donné** la documentation opérateur et les points d’entrée CLI  
**Quand** on compare assessment, `preflight` et `diagnose`  
**Alors** leurs rôles sont distincts : pré-adoption / réconciliation pré-compile / pré-Run / post-install opérationnel.

### ADO-AC-008 — Waive sans trace refusé

**Étant donné** un constat `blocking` marqué `waive` sans référence d’autorisation humaine  
**Quand** le verdict est calculé  
**Alors** le constat reste bloquant et le verdict ne peut pas être `go`.

### ADO-AC-009 — Brownfield code métier intact

**Étant donné** une cible avec `src/`, `docs/`, `README.md`, `requirements.txt` racine non framework  
**Quand** assessment puis (après Décision) install fraîche réussie selon politique en vigueur  
**Alors** ces fichiers métier restent inchangés par l’assessment ; l’install respecte le layout Document 11 §4 (déjà couvert par les tests distribution brownfield).

### ADO-AC-010 — Documentation adoptant

**Étant donné** le guide [adoption-assessment.md](../../adopter-guide/adoption-assessment.md) et la checklist adoptant  
**Quand** un opérateur prépare une première install  
**Alors** la séquence Assessment → Décision → Install → matière/inventaire as-built → G0/compile est décrite sans exiger la lecture du code source.

### ADO-AC-011 — Baseline brownfield

**Étant donné** une cible avec une racine de code applicatif non vide (`src/` ou équivalent) et sans `docs/product/`  
**Quand** l’assessment produit un rapport  
**Alors** la catégorie `baseline` contient au moins les constats d’inventaire as-built et d’écart de matière produit (`warning`), et le verdict ne peut être un `go` pur tant que ces warnings restent `unresolved`.

## 3. Preuves attendues

| Critère | Preuve minimale |
|---|---|
| ADO-AC-001 à 004, 008, 011 | Test automatisé (CLI ou bibliothèque Distribution) + sortie rapport |
| ADO-AC-005, 006, 007, 010 | Revue documentaire + éventuel test de contrat de sortie |
| ADO-AC-009 | Réutilisation / extension des tests brownfield distribution |

## 4. Limites

- Les constats `authority` entièrement automatiques (CI distante, branch protection vendeur, etc.) peuvent rester partiels ; ADO-AC-005 accepte des constats « à confirmer par l’opérateur » (`operator_confirmation_required`).
- La détection `baseline` est heuristique (racines de code / `docs/product/`) ; elle n’audite pas le contenu sémantique des sources.
- Le contournement `--skip-assessment-gate` / `GOVERNED_AI_SKIP_ASSESSMENT_GATE=1` est un bypass humain explicite, pas un mode hybride.

## Références

- Document 19 — Gouvernance exclusive et assessment d’adoption
- Document 14 — Tests de conformité (cycle installé)
- [adopter-checklist.md](../../adopter-guide/adopter-checklist.md)
