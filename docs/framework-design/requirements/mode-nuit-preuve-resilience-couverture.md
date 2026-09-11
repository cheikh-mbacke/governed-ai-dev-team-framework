# Mode nuit — état des lieux de la preuve de résilience (§15)

**Statut** : **essai L4 réel échoué / écarts observés** (exports feedback
`sads-ecosystem-backend`, 10–11 septembre 2026). La couverture fonctionnelle
automatisée des 14 scénarios §15 reste en place, mais **ne doit plus être lue
comme une preuve L4**. Un witness run non supervisé de plusieurs heures, après
correction des écarts ci-dessous, est requis avant toute reprise d'annonce L4.

Ce document répond à une question précise : sur les 14 scénarios de résilience
listés au §15 de la spécification *« Document 6 — Autonomie avancée et exécution
non supervisée (mode nuit) »* (fichier utilisateur
`autonomie-avancee-mode-nuit-spec.md`, hors dépôt), lesquels sont aujourd'hui
vérifiés par les tests, et avec quel degré de réalisme. Conformément au §15, un
test de fonction ou un sous-processus court ne doit pas être présenté comme un
run non supervisé réel de plusieurs heures.

Ce numéro de document (« Document 6 ») appartient à la numérotation propre de
cette spécification mode nuit, distincte de la numérotation
`docs/framework-design/**/NN-*.md` déjà utilisée dans ce dépôt (où le Document 05
est *Résolution des écarts du protocole* et le Document 06 est *Catalogue des
contrats de rôle* — sans rapport avec le mode nuit). Aucun renommage n'a été
fait pour éviter la confusion : ce fichier reste volontairement hors de cette
numérotation.

## 0. Écarts observés sur l'essai L4 réel (sept. 2026)

Sources : exports JSON sous `Downloads/feedback` (anonymisés en fixtures
`tests/fixtures/learning/exports/`). Sur le dernier export du projet observé :

- 13 tentatives enregistrées, 0 terminale `succeeded` ;
- timeouts d'implémentation à ~600 s puis relances ;
- deux timeouts parallèles traités comme panne systémique ;
- handoffs agent en prose + JSON rejetés ;
- preuves AC-* rejetées faute du check nommé `implementation` ;
- écritures `.ai-team/evidence/**` refusées comme hors scope ;
- run `idle` avec attempts `started` orphelines.

Correctifs livrés sur `renov/installed-runtime-portability` (Lots 1–5 + suite) :
portabilité runtime, handoff/evidence, boundary evidence, timeouts/WIP/taxonomie,
`no_dispatchable_work`, dédup feedback, `context_package_ref` + complétude.
**Ces correctifs ne reconstituent pas à eux seuls un witness L4** : il faut un
nouveau run réel multi-heures archivé avant de retirer le statut d'échec.

| Écart observé | Scénario §15 touché | Correctif code | Preuve L4 encore manquante |
|---|---|---|---|
| Timeout 600 s trop court / pas de WIP | #2 | timeouts par étape + checkpoint unverified | run réel multi-heures avec timeout long |
| Timeouts parallèles → stop systémique | #6 / #12 | `failure_scope` work_unit ; signature systémique | witness avec 2 WU timeout indépendantes |
| Handoff prose + JSON | #2 (qualité résultat) | `extract_governed_handoff` | CLI Cursor réel post-fix |
| Evidence gate nom `implementation` | (hors §15 strict) | AC-* + SHA + artefacts | idem |
| Boundary evidence gouvernée | (hors §15 strict) | allowlist `.ai-team/evidence/<WU>/**` | idem |
| Idle / orphans `started` | #1 / #14 | recovery + `no_dispatchable_work` | redémarrage process hôte réel |

## 1. Ce qui a été construit (rappel factuel)

**Couche 1 — moteur de règles déterministes** (étapes 1 à 9 du §14) :
`src/governed_ai/core/domain/run/`, handlers Run/Grant/Checkpoint, vérifiée par
les tests `tests/core/test_run_handlers.py`. Ces tests reconstituent chaque
scénario en écrivant directement l'état voulu plutôt que d'attendre réellement —
ils prouvent que **la règle est correcte une fois la condition atteinte**, pas
que **le système détecte la condition en production**.

**Couche 2 — orchestrateur exécutable** (étape 10 du §14) :
`src/governed_ai/core/orchestrator/tick.py`, `git_workspace.py`,
`adapters/cursor/runtime/agent_cli.py`. Le lancement natif reste opt-in via
`GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1`. Les tests exercent des processus et
Git, mais pas une mission réelle de plusieurs heures.

Le seul élément qui reste une simulation assumée, documentée en tête de
`tick.py` : aucun test ne fait tourner l'orchestrateur pendant des heures
réelles. `scripts/ai-team/orchestrate.py` est hors du périmètre unitaire.

## 2. Tableau de couverture

| # | Scénario (§15) | Couverture automatisée | Preuve existante | Ce qu'il manque pour une preuve L4 réelle |
|---|---|---|---|---|
| 1 | Crash et redémarrage | Couvert (tick) | `test_restart_resumes_from_persisted_checkpoint` ; recovery attempts orphelines | Tuer le process hôte `orchestrate.py` au niveau OS |
| 2 | Timeout agent | Couvert (watchdog + timeouts policy) | `test_agent_watchdog_kills_a_real_timed_out_process` ; timeouts par étape | Timeout long réel + WIP observé sur CLI Cursor |
| 3 | Perte de heartbeat | Couvert (temps simulé) | `test_tick_reassigns_a_stale_lease` | Attente réelle de `stalled_after_minutes` |
| 4 | Fencing worker réattribué | **Couvert** | tests fencing Core | — |
| 5 | Conflit Git merge queue | **Couvert** | `test_real_merge_conflict_is_detected_and_aborted` | — |
| 6 | Test flaky vs systémique | Couvert (renforcé) | flaky retry + taxonomie timeout non systémique | Witness 2 WU timeout sans stop run |
| 7 | Remédiations infructueuses | **Couvert** | convergence / demote | — |
| 8 | Permission manquante | Couvert | `test_adapter_permission_failure_pauses_work_unit` | — |
| 9 | Au-delà execution_ceiling | **Couvert** | handlers ceiling | — |
| 10 | Désescalade refusée | **Couvert** | tighten / pas de loosen | — |
| 11 | Décision humaine partielle | **Couvert** | subgraph decision | — |
| 12 | global_stop_condition + alerte | Couvert | close_run alert ; `no_dispatchable_work` | Notification humaine réelle |
| 13 | WU en parallèle | Couvert (réserve timing) | concurrent ticks | — |
| 14 | Reprise lendemain | Couvert (état) | checkpoint + morning report | Écart d'horloge murale réel |

## 3. Lecture synthétique

- **Couverture fonctionnelle automatisée** : les 14 scénarios ont au moins une
  preuve ciblée de règle ou mécanisme. **Ce n'est pas la preuve L4** du §15.
- **Essai L4 réel (sept. 2026)** : échec / non-convergence par faux négatifs de
  gouvernance — statut documentaire : *essai L4 réel échoué / écarts observés*
  jusqu'à un nouveau witness multi-heures.
- Les exports anonymisés sous `tests/fixtures/learning/exports/` servent de
  non-régression (dédup agrégat) et non de preuve d'autonomie.
- Tant qu'un protocole L4 archivé n'existe pas, le mode nuit doit être décrit
  comme **implémenté, testé unitairement, et non encore éprouvé L4**.
