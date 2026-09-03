# Document 10 — Modèle tactique : Feedback/Apprentissage

**Statut** : version 1.3 — aligné ADR-009 (usage = acceptation).

## 1. Réalité observée

### Observation

Le schéma accepte `open`, `acknowledged`, `candidate_change`, `resolved` et `rejected`, ainsi que `resolution` et `classification.origin`. `feedback.py record` crée cependant toujours un nouveau fichier et n’offre aucune commande de transition. Les statuts peuvent être fournis dès la création ; l’ordre d’un cycle de vie n’est pas imposé.

Conclusion : le dépôt possède un **Observation Record dont le schéma prévoit des états**, pas encore un Agrégat mutable opérationnel.

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
- l’orchestrateur déclenche cette soumission en best-effort à la clôture d’un Run.

Quand `collection` vaut `disabled`, aucune soumission sortante n’est tentée (exception hors ligne).

Le `project_ref` reste un identifiant d’installation (`telemetry.project_ref`) ; le `project_id` réel est aussi transmis sous `consented_share`.

## 2. Cible Observation

Observation devient un Agrégat seulement si les éléments suivants sont implémentés :

- racine identifiée par `observation_id` ;
- commandes `RecordObservation`, `AcknowledgeObservation`, `QualifyObservation`, `ResolveObservation`, `RejectObservation` ;
- transitions permises et autorité de chaque commande ;
- mise à jour atomique et contrôle de concurrence ;
- événement immuable après transition réussie.

`record_observation` doit être accessible aux Rôles en lecture seule par un port médié. Le champ texte `recorded_by` n’accorde aucune capacité technique à lui seul.

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

- Les commandes de transition d’Observation et de revue de Retrospective n’existent toujours pas. L’orchestrateur déclenche `RecordObservation` sur échec/timeout/blocage, `GenerateRetrospective` à la clôture WU/Run, et `SubmitFeedback` à la clôture de Run sous `consented_share`.
- Sous `consented_share`, ADR-009 impose l’absence de précaution de contenu sur le Feedback Export transmis.

## Sources

`.ai-team/schemas/observation.schema.json`, `retrospective.schema.json`, `feedback-export.schema.json`, `scripts/ai-team/feedback.py`, ADR-009.
