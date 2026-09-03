# Document 10 — Modèle tactique : Feedback/Apprentissage

**Statut** : version 1.5 — coalesce + `TransitionObservation`.

## 1. Réalité observée

### Observation

`RecordObservation` crée un fichier Observation, ou **fusionne** (coalesce) un
sighting supplémentaire lorsqu’une Observation non résolue partage le même
`recurrence_key` et le même `work_unit` : `occurrence_count` augmente,
`last_recorded_at` et les preuves sont mis à jour, le symptôme initial est
conservé. Une Observation déjà `resolved`/`rejected` ne fuse pas : un nouvel
épisode est créé.

`TransitionObservation` (Control Plane) applique une machine à états
avant-seulement :

- `open` → `acknowledged` | `candidate_change` | `resolved` | `rejected`
- `acknowledged` → `candidate_change` | `resolved` | `rejected`
- `candidate_change` → `resolved` | `rejected`

`resolved` / `rejected` exigent une `resolution` non vide. Une mise à jour
optionnelle de `classification` (origine + confiance) est permise dans la même
commande. La concurrence utilise `revision` / `expected_revision` (défaut `1`
si le champ est absent sur un artefact legacy).

Conclusion : Observation est un **Agrégat mutable opérationnel** pour la
récurrence et le cycle de statut ; le statut fourni à la seule création reste
un raccourci (pas une transition).

### Retrospective

Le script génère un snapshot `generated` pour une Work Unit ou un projet. Il ne propose pas de commande `review` et le schéma n’empêche pas une modification manuelle du contenu.

Conclusion : la Retrospective se comporte actuellement comme un rapport/snapshot persisté. Son évolution `generated` → `reviewed` est seulement prévue par le schéma.

### Feedback Export et transmission

L’export est au format `1.2` (`export_id`, `transmission`). Par défaut il est aussi conservé sous `.ai-team/metrics/framework-feedback-*.json`.

**Installer ou utiliser le framework vaut acceptation** (ADR-009). Il n’y a pas de mode privacy intermédiaire : le choix de l’adoptant est d’utiliser le framework ou de ne pas l’utiliser.

Quand `telemetry.collection` vaut `consented_share` (défaut à l’installation) :

- l’export **full** avec `project_id` est le défaut ;
- **aucune** anonymisation, **aucune** `human_authorization` par export, **aucune** restriction de contenu Feedback ;
- `SubmitFeedback` pousse l’artefact vers `telemetry.submit_url` (ou l’outbox locale si l’URL est absente) ;
- l’orchestrateur déclenche cette soumission en best-effort à **toute** clôture
  terminale de Run (`completed` **et** `stopped`) ;
- un échec réseau ou l’absence d’URL laisse l’export sous
  `.ai-team/metrics/outbox/` ; `feedback.py flush-outbox` (et chaque
  `SubmitFeedback`) retente la transmission.

Quand `collection` vaut `disabled`, aucune soumission sortante n’est tentée (exception hors ligne).

Le `project_ref` reste un identifiant d’installation (`telemetry.project_ref`) ; le `project_id` réel est aussi transmis sous `consented_share`.

## 2. Cible Observation

Observation est un Agrégat lorsque :

- racine identifiée par `observation_id` ;
- commandes `RecordObservation` (création / coalesce) et `TransitionObservation` ;
- transitions permises et autorité Control Plane ;
- mise à jour atomique via le Command Gateway et `revision` / `expected_revision`.

Les commandes séparées `AcknowledgeObservation` / `QualifyObservation` /
`ResolveObservation` / `RejectObservation` restent une option de décomposition ;
`TransitionObservation` couvre aujourd’hui ces effets via `to_status` et une
`classification` optionnelle.

`record_observation` doit rester accessible aux Rôles en lecture seule par un
port médié. Le champ texte `recorded_by` n’accorde aucune capacité technique à
lui seul.

## 3. Cible Retrospective

Deux options sont valides ; l’implémentation doit en choisir une :

1. **Snapshot immuable + Review séparée** : contenu figé, décision de revue dans un enregistrement distinct ; option privilégiée pour l’audit.
2. **Agrégat Retrospective** : seule la transition de statut est autorisée, la commande `ReviewRetrospective` vérifie que le contenu n’a pas changé.

Les scopes actuels sont `work_unit` et `project`. Le scope `increment` est retiré du langage courant tant qu’un identifiant, un schéma et une commande ne sont pas définis.

## 4. Relation à Gouvernance

Une Retrospective compte ou référence observations, events/messages, décisions, findings, acceptances et Work Units. Feedback adopte les identifiants Gouvernance sans les modifier, mais produit son propre modèle de synthèse. Le pattern Conformist est donc limité aux identifiants et contrats de lecture, pas à toute la sémantique.

## 5. Repositories et stockage

| Objet | Stockage actuel |
|---|---|
| Observation | `.ai-team/observations/{id}.yaml` |
| Retrospective | `.ai-team/retrospectives/{id}.yaml` |
| Feedback Export | `.ai-team/metrics/framework-feedback-*.json` par défaut, ou chemin fourni. |
| Outbox / transmis | `.ai-team/metrics/outbox/` puis destination `telemetry.submit_url` ; ingest framework sous `learning/inbox/`. |

## 6. Limites

- La revue de Retrospective (`ReviewRetrospective`) n’existe toujours pas.
  L’orchestrateur déclenche `RecordObservation` sur échec/timeout/blocage (avec
  coalesce sur `auto:{step}:{status}`), `GenerateRetrospective` à la clôture
  WU/Run, et `SubmitFeedback` à toute clôture terminale de Run (`completed` ou
  `stopped`) sous `consented_share`. L’outbox locale est retentée via
  `flush-outbox` / `SubmitFeedback`.
- Sous `consented_share`, ADR-009 impose l’absence de précaution de contenu sur le Feedback Export transmis.

## Sources

`.ai-team/schemas/observation.schema.json`, `retrospective.schema.json`, `feedback-export.schema.json`, `scripts/ai-team/feedback.py`, ADR-009.
