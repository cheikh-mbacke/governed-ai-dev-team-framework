# Mode nuit — état des lieux de la preuve de résilience (§15)

> **Verdict L4 : non validé.**
>
> Un **essai L4 réel a échoué** (exports feedback du 10–11 septembre 2026).
> La résilience « mode nuit » **ne doit pas** être présentée comme éprouvée L4.
> Les tests unitaires / d’intégration ci-dessous prouvent des *règles et
> mécanismes*, pas un run non supervisé de plusieurs heures.

**Statut documentaire** : `essai_L4_reel_echoue` — écarts observés encore
référencés ; correctifs code livrés sur la branche de rénovation, **sans**
nouveau witness L4 archivé.

Ce document répond à une question précise : sur les 14 scénarios de résilience
listés au §15 de la spécification *« Document 6 — Autonomie avancée et exécution
non supervisée (mode nuit) »* (fichier utilisateur hors dépôt), lesquels ont
aujourd’hui une **preuve automatisée de règle**, et avec quel degré de réalisme.
Conformément au §15, un test de fonction ou un sous-processus court **n’est
pas** un run non supervisé réel de plusieurs heures.

Ce numéro de document (« Document 6 ») appartient à la numérotation propre de
cette spécification mode nuit, distincte de la numérotation
`docs/framework-design/**/NN-*.md` du dépôt.

## 0. Essai L4 réel — échec et écarts observés

### 0.1 Preuves anonymisées (non-régression, pas preuve L4)

Les exports bruts du run réel ne sont **pas** versionnés. Une forme anonymisée,
qui conserve les relations utiles (`revision`, `snapshot_sequence`, doublons
d’identités, `recurrence_key`) tout en retirant identifiants projet/provider,
chemins locaux, transcripts et textes libres, est déposée ici :

- `tests/fixtures/learning/exports/EXP-ANON-*.json`
- `tests/fixtures/learning/MANIFEST.json`
- régénération : `python tools/anonymize_feedback_fixtures.py --source <raw>`
- test : `tests/test_learning_anon_fixtures.py`

Ces fixtures **ne vivent pas** sous `tests/fixtures/projects/clean|legacy/`.
Elles servent uniquement à régresser l’agrégation / dédup feedback, **pas** à
attester qu’un mode nuit multi-heures a réussi.

### 0.2 Écarts observés (symptômes du run réel)

Sur le dernier snapshot du projet client observé (anonymisé) :

- 13 tentatives enregistrées, **0** terminale `succeeded` ;
- timeouts d’implémentation trop courts puis relances ;
- deux timeouts parallèles traités comme panne systémique ;
- handoffs agent en prose + JSON rejetés ;
- preuves AC-* rejetées faute du check nommé exactement `implementation` ;
- écritures `.ai-team/evidence/**` refusées comme hors scope ;
- run resté `idle` avec attempts `started` orphelines.
- processus orchestrateur vivant mais sans progrès utile pendant plusieurs heures ;
- checks QA/audit valides rejetés à cause d'un vocabulaire de transport caché ;
- rôle d'implémentation backend imposé à des Work Units frontend ;
- grant annonçant des chemins de gouvernance ensuite refusés par le boundary ;
- crash orchestrateur non terminal et absence de recovery externe autonome.

### 0.3 Correctifs code ≠ validation L4

Des correctifs ont été livrés (portabilité, handoff/evidence, boundary,
timeouts/WIP/taxonomie, recovery orphans / `no_dispatchable_work` /
`awaiting_human`, dédup feedback, context package). **Ils ne remplacent pas**
un witness L4 : tant qu’un nouvel essai réel multi-heures n’est pas exécuté et
archivé, le statut reste **échec / non validé**.

| Écart observé | Scénario §15 | Correctif code (si présent) | Toujours manquant pour L4 |
|---|---|---|---|
| Timeout trop court / pas de WIP sûr | #2 | timeouts par étape ; WIP après contrôle de périmètre | Run réel multi-heures + WIP observé |
| Timeouts parallèles → stop systémique | #6 / #12 | taxonomie `failure_scope` | Witness 2 WU timeout sans stop run |
| Handoff prose + JSON | (qualité résultat) | `extract_governed_handoff` | CLI Cursor réel post-fix |
| Evidence gate nom `implementation` | — | AC-* + SHA + artefacts | Idem |
| Boundary evidence gouvernée | — | allowlist evidence WU | Idem |
| Idle / orphans / attente humaine | #1 / #14 | recovery + `no_dispatchable_work` + `awaiting_human` + Supervisor Daemon | Redémarrage process hôte réel |
| Liveness sans progrès | #1 / #3 / #12 | `stalled_no_progress` ignore les heartbeats seuls | Witness multi-heures post-fix |
| Crash du process | #1 / #12 | fermeture `orchestrator_process_failure` + watchdog / daemon | Kill process hôte réel |
| Rôle frontend ignoré | staffing | rôle dérivé staffing/contexte/zone | Dispatch Cursor réel post-fix |
| Double vocabulaire de checks | qualité résultat | aliases bornés + `required_checks` explicites dans le prompt | Handoffs réels post-fix |
| Grant/boundary contradictoires | #8 / #9 | chemins Control Plane filtrés à l'émission et au dispatch | Grant réel post-fix |

### 0.4 Conditions d’un nouvel essai L4

Avant de retirer le statut `essai_L4_reel_echoue`, **toutes** les conditions
suivantes doivent être réunies et archivées :

1. Run non supervisé réel de **plusieurs heures** (`orchestrate.py` + CLI
   Cursor opt-in), pas seulement des appels unitaires à `run_scheduling_tick`.
2. Au moins deux Work Units indépendantes avec timeouts / reprises WIP sans
   arrêt systémique abusif.
3. Handoffs agent réels (prose éventuelle) acceptés ou rejetés explicitement
   avec preuve.
4. Evidence et boundary : preuves sous `.ai-team/evidence/<WU>/` acceptées ;
   chemins hors périmètre refusés **avant** tout commit durable.
5. Arrêt propre : `no_dispatchable_work` ou `awaiting_human` selon l’état,
   recovery des `started` orphelines au redémarrage process.
6. Export feedback anonymisé déposé sous `tests/fixtures/learning/` (ou
   successeur) + mise à jour de ce document avec le lien et le SHA du witness.
7. Watchdog indépendant **ou** Supervisor Daemon observé : détection du
   process mort ou de `stalled_no_progress`, récupération plafonnée, puis
   résultat explicite `recovered`, `needs_human` ou `abandoned`. Le daemon
   (`scripts/ai-team/daemon.py`) est le propriétaire opérationnel recommandé ;
   `night_watchdog.py` reste un détecteur externe compatible.

Sans ce paquet de preuves, toute formulation du type « résilience L4 validée »
est **interdite**.

## 1. Ce qui a été construit (rappel factuel — hors L4)

**Couche 1 — moteur de règles déterministes** (étapes 1 à 9 du §14) :
`src/governed_ai/core/domain/run/`, handlers Run/Grant/Checkpoint, tests
`tests/core/test_run_handlers.py`. Preuve de *règle une fois la condition
atteinte*, pas de détection en production sur plusieurs heures.

**Couche 2 — orchestrateur exécutable** :
`tick.py`, `git_workspace.py`, `agent_cli.py`. Lancement natif opt-in
`GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1`. Aucun test unitaire ne fait tourner
l’orchestrateur pendant des heures réelles.

## 2. Tableau de couverture automatisée (≠ preuve L4)

Légende : « règle couverte » = test ciblé de mécanisme. **Aucune ligne de ce
tableau n’autorise à dire que le mode nuit est validé L4.**

| # | Scénario (§15) | Règle couverte (auto) | Preuve existante | Manque pour L4 réel |
|---|---|---|---|---|
| 1 | Crash / redémarrage | partielle (process + tick) | reprise checkpoint ; recovery orphans ; watchdog/recovery plafonné | Kill process hôte `orchestrate.py` |
| 2 | Timeout agent | partielle | watchdog ; timeouts policy ; WIP post-boundary | Timeout long réel + WIP CLI |
| 3 | Perte de heartbeat / faux healthy | partielle (temps simulé) | réattribution lease ; liveness distincte du progrès | Attente réelle `stalled_after_minutes` |
| 4 | Fencing | oui (Core) | tests fencing | — |
| 5 | Conflit Git | oui | merge abort réel | — |
| 6 | Flaky vs systémique | partielle | taxonomie timeout non systémique | Witness 2 WU |
| 7 | Remédiations | oui | convergence | — |
| 8 | Permission manquante | oui | pause WU | — |
| 9 | execution_ceiling | oui | handlers | — |
| 10 | Désescalade refusée | oui | tighten only | — |
| 11 | Décision humaine partielle | oui | subgraph | — |
| 12 | global_stop + alerte | partielle | close_run ; `no_dispatchable_work` | Notification humaine réelle |
| 13 | WU en parallèle | partielle | concurrent ticks | — |
| 14 | Reprise lendemain | partielle (état) | checkpoint + morning report | Horloge murale réelle |

## 3. Lecture synthétique (obligatoire)

- **L4 non validé** — essai réel en échec ; statut `essai_L4_reel_echoue`.
- Les 14 scénarios ont des preuves *automatisées de règle* ; **ce n’est pas**
  la preuve L4 du §15.
- Les exports anonymisés (`tests/fixtures/learning/`) documentent les
  relations du run raté pour la non-régression feedback ; ils **ne
  constituent pas** une preuve d’autonomie réussie.
- Formulations interdites tant que §0.4 n’est pas satisfait :
  « résilience L4 validée », « mode nuit éprouvé », « end-to-end L4 OK ».
- Formulation autorisée : **implémenté et testé unitairement ; essai L4 réel
  échoué ; en attente d’un nouveau witness multi-heures**.
