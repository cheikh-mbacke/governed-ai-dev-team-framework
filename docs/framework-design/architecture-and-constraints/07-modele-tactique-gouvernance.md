# Document 7 — Modèle tactique du domaine cœur Gouvernance

**Statut** : version 1.1 corrigée. Les classifications sont indiquées comme observées, candidates ou cibles ; un fichier ou un champ `status` ne suffit pas à démontrer un Agrégat.

## 1. Agrégats candidats

| Candidat | Identité | Invariants à imposer pour confirmer l’Agrégat |
|---|---|---|
| **Work Unit** | `WU-*` | Transitions de statut, dépendances, preuves liées au bon SHA, outcomes cohérents et transition `done` atomique. C’est le candidat le mieux étayé. |
| **Decision Request** | id de décision | Options, autorité, transitions `pending_human` → `decided`/`cancelled`, décision non ambiguë. Le writer manque. |
| **Finding** | id | Transitions et autorité de remédiation. |
| **Release Candidate** | id | Cohérence du commit, des Work Units et des preuves requises. |
| **Acceptance** | id | Autorité humaine et rattachement exact au candidat. |

`Project Profile`, `Source Registry`, `Context Package` et `Project State` sont des enregistrements persistés importants. Leur qualification d’Agrégat reste ouverte tant que leurs commandes, invariants et frontières transactionnelles ne sont pas définis. Project State est directement écrit ; il n’est pas aujourd’hui une projection entièrement reconstructible.

## 2. Evidence et StructuredEvent

- **Evidence** n’a pas de `status` racine. Son immutabilité est une règle cible à imposer par repository append-only ou remplacement interdit ; le schéma seul ne la garantit pas.
- **StructuredEvent** exige un champ `status`. Il ne peut donc pas être qualifié en bloc de fait immuable.

Les dix types actuels — `STATUS`, `CONTEXT_REQUEST`, `CLARIFICATION_REQUEST`, `DECISION_REQUEST`, `BLOCKER`, `CONTRACT_CHANGE`, `REVIEW_REQUEST`, `DEFECT`, `SKILL_REQUEST`, `HANDOFF` — mélangent faits, demandes et messages de workflow.

La cible les sépare :

1. **Domain Event** : fait passé, immuable, émis après réussite transactionnelle ;
2. **Request/Command** : demande d’action qui peut être acceptée ou refusée ;
3. **Workflow Message** : coordination opérationnelle éventuellement mutable.

`outcomes.defects` est aujourd’hui un tableau non typé. Il n’est pas établi qu’il référence nécessairement un StructuredEvent `DEFECT`. De même, aucun invariant n’impose le lien entre une Decision Request et un message `DECISION_REQUEST`.

## 3. Gate Decision : état réel

Le handler `RecordGateDecision` (via `scripts/ai-team/gov.py command`) applique les décisions de gate dans une unité transactionnelle cible. L’ancien script `record_gate.py` a été **supprimé en 0.6.0** ; les écritures directes non transactionnelles décrites ci-dessous concernent l’audit legacy pré-Phase 3 :

- Project State est écrit avant le fichier de décision ;
- les écritures ne sont pas transactionnelles ;
- le nom de fichier n’a qu’une résolution à la seconde et peut être écrasé ;
- aucun projecteur ne reconstruit Project State ou Work Unit depuis les décisions ;
- G4 peut marquer le projet `completed` sans Work Unit et sans démontrer toutes les acceptations.

### Cible

Soit Gate Decision devient un journal append-only fiable avec identifiant unique dans le nom, écriture atomique, idempotence et projecteur testé ; soit le système cesse de le présenter comme source de vérité et désigne explicitement l’état transactionnel comme source. Dans les deux cas, une seule commande doit valider puis appliquer la décision.

## 4. Frontières de persistance observées

| Objet | Chemin observé ou validé |
|---|---|
| Work Unit | `.ai-team/work-units/{id}.yaml` |
| Project State | `.ai-team/state/project-state.yaml` |
| Gate Decision | `.ai-team/decisions/gate-{gate}-{horodatage}.yaml` |
| Decision Request | Répertoire `.ai-team/decisions/` et template confirmés ; writer et nom exact ouverts. |
| Evidence | `.ai-team/evidence/` |
| Finding | `.ai-team/findings/` |
| StructuredEvent | `.ai-team/events/` |
| Release Candidate | `.ai-team/releases/` |
| Acceptance | `.ai-team/acceptance/` |
| Context Package | `.ai-team/context-packages/` |
| Project Profile | `.ai-team/project-profile.yaml` |
| Source Registry | `.ai-team/sources/source-registry.yaml` |

Ces chemins sont des frontières de persistance observées, pas à eux seuls des Repositories DDD. Un Repository doit également offrir les opérations et protéger les invariants de l’Agrégat.

## 5. Limites

- Les dossiers ne contiennent pas d’instances YAML métier dans ce dépôt gabarit ; `.ai-team/logs/cursor-events.jsonl` constitue seulement une trace runtime.
- Le writer de Decision Request reste à définir.
- Les transitions, transactions et règles d’immutabilité cibles ne sont pas implémentées.

## Sources

Schémas Gouvernance sous `.ai-team/schemas/`, `scripts/ai-team/gov.py`, `validate.py`, `.ai-team/templates/decision-request.yaml`, DDD Reference d’Eric Evans.
