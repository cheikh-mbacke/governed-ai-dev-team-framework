# Document 10 — Modèle tactique : Feedback/Apprentissage

**Statut** : version 1.1 corrigée. Le modèle observé et la cible sont séparés.

## 1. Réalité observée

### Observation

Le schéma accepte `open`, `acknowledged`, `candidate_change`, `resolved` et `rejected`, ainsi que `resolution` et `classification.origin`. `feedback.py record` crée cependant toujours un nouveau fichier et n’offre aucune commande de transition. Les statuts peuvent être fournis dès la création ; l’ordre d’un cycle de vie n’est pas imposé.

Conclusion : le dépôt possède un **Observation Record dont le schéma prévoit des états**, pas encore un Agrégat mutable opérationnel.

### Retrospective

Le script génère un snapshot `generated` pour une Work Unit ou un projet. Il ne propose pas de commande `review` et le schéma n’empêche pas une modification manuelle du contenu.

Conclusion : la Retrospective se comporte actuellement comme un rapport/snapshot persisté. Son évolution `generated` → `reviewed` est seulement prévue par le schéma.

### Feedback Export

L’export est un artefact sans `status`, au format `1.0`. Par défaut, il est conservé sous `.ai-team/metrics/framework-feedback-*.json`. Il n’est donc pas seulement « destiné à quitter le projet ».

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

Pour l’export, la cible impose une commande humaine ou un consentement vérifiable, un choix anonymisé/complet, un contrôle des données sensibles et une politique de rétention. Aucun de ces contrôles n’est présenté comme déjà implémenté.

## 6. Limites

- Les dossiers Observation et Retrospective du gabarit ne contiennent pas d’instances métier.
- Les commandes de transition et de revue n’existent pas.
- Le consentement export n’est pas imposé par le script actuel.
- La politique de conservation de `.ai-team/metrics/` reste à définir.

## Sources

`.ai-team/schemas/observation.schema.json`, `retrospective.schema.json`, `feedback-export.schema.json`, `scripts/ai-team/feedback.py`, `tools/install.py:PROJECT_OWNED_PATTERNS`.
