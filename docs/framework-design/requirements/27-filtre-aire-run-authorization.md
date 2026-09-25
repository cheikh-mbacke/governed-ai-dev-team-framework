# Document 27 — Filtre d’aire sur RunAuthorizationGrant

**Statut** : version 1.1 — exigence normative ; implémentée dans le noyau
(`IssueRunAuthorizationGrant`, `OpenRun`, tick / dispatch).

Les termes **DOIT**, **NE DOIT PAS**, **DEVRAIT** et **PEUT** expriment une
obligation, une interdiction, une recommandation forte et une option.

## 1. Problème

Les Work Units portent déjà une classification `zone.area`
(`frontend`, `backend`, `fullstack`, `mobile`, `infra`, `data`, `unknown`).
Le staffing et la résolution de rôle s’en servent. En revanche, un
`RunAuthorizationGrant` ne contraint le Run que par une liste explicite de
`work_unit_ids` (et par des plafonds d’exécution).

Pour un run planifié ou non supervisé, l’humain veut souvent un **périmètre de
confiance déclaratif** — par exemple « uniquement backend » — sans énumérer
manuellement chaque Work Unit à chaque grant, et sans risquer qu’un tick
dispatch une Work Unit d’une autre aire.

L’absence de ce filtre a déjà contribué à des écarts observés en mode nuit
(rôle d’implémentation backend imposé à des Work Units frontend — voir
`mode-nuit-preuve-resilience-couverture.md`).

## 2. Décision

Étendre `RunAuthorizationGrant` d’un axe optionnel **`allowed_areas`**,
évalué mécaniquement à l’émission du grant, à `OpenRun` et à chaque dispatch
éligible. Cet axe complète `work_unit_ids` ; il ne le remplace pas.

Ne **PAS** introduire un second vocabulaire « type de tâche » parallèle à
`zone.area`. Ne **PAS** confondre le filtre d’aire avec un filtre de rôles
(`backend-developer` seul) : QA, revue et audit restent soumis au staffing.

## 3. Modèle

### 3.1 Champ `allowed_areas`

| Propriété | Règle |
|---|---|
| Type | tableau de chaînes, sous-ensemble de l’enum `WorkUnit.zone.area` **hors** `unknown` |
| Présence | optionnelle ; absente ou `null` ⇒ aucun filtre d’aire (comportement actuel) |
| Vide | interdit si le champ est présent : un filtre déclaré DOIT nommer au moins une aire |
| Intersection | une Work Unit est **aire-éligible** ssi `zone.area ∈ allowed_areas` |

Valeurs autorisées dans `allowed_areas` :
`frontend`, `backend`, `fullstack`, `mobile`, `infra`, `data`.

### 3.2 Intersection avec `work_unit_ids`

1. `work_unit_ids` reste **obligatoire** et non vide (contrat actuel Document 6 §8).
2. Quand `allowed_areas` est présent, chaque id listé DOIT référencer une Work Unit
   dont `zone.area` est dans `allowed_areas` au moment de
   `IssueRunAuthorizationGrant` ; sinon l’émission **échoue**.
3. `OpenRun` DOIT refuser tout `payload.work_unit_ids` qui n’est pas à la fois
   couvert par le grant **et** aire-éligible.
4. Le tick / dispatch DOIT ignorer (ne pas acquérir, ne pas dispatcher) toute
   Work Unit du Run devenue hors filtre — notamment si `zone.area` a changé
   depuis l’émission — et enregistrer la raison machine
   `area_filter_mismatch`.

### 3.3 `fullstack` et multi-aire

- Inclure `fullstack` dans `allowed_areas` est **explicite** : ce n’est pas
  impliqué par `frontend` ni par `backend`.
- Une Work Unit `fullstack` n’est éligible que si `fullstack ∈ allowed_areas`.
- Le filtre d’aire **NE DOIT PAS** élargir silencieusement le périmètre pour
  « terminer » une dépendance d’une autre aire.

### 3.4 Dépendances hors filtre

Quand une Work Unit aire-éligible dépend d’une Work Unit hors filtre :

| Politique | Comportement | Quand |
|---|---|---|
| `skip_blocked` (défaut) | La WU dépendante reste non dispatchable ; le Run continue sur les WU indépendantes éligibles ; stop `no_dispatchable_work` si plus rien n’est faisable | Runs partiels / « ce soir backend seulement » |
| `stop_on_cross_area_dependency` | Le Run s’arrête avec `stop_condition: cross_area_dependency` dès qu’une WU éligible est bloquée uniquement par une dépendance hors filtre | Runs qui exigent un graphe fermé |

La politique DOIT être déclarée sur le grant (`area_filter_dependency_policy`,
défaut `skip_blocked`). Elle **NE DOIT PAS** être choisie librement par un rôle
d’exécution.

### 3.5 `unknown`

- `unknown` **NE DOIT PAS** apparaître dans `allowed_areas`.
- Une Work Unit avec `zone.area = unknown` **N’EST JAMAIS** aire-éligible
  quand un filtre est actif.
- À la compile / G1, le Control Plane **DEVRAIT** refuser ou escalader les
  Work Units `unknown` destinées à un run filtré, plutôt que de les laisser
  silencieusement hors dispatch.

## 4. Exigences fonctionnelles

| ID | Exigence |
|---|---|
| AREA-F-001 | Le schéma `RunAuthorizationGrant` DOIT admettre `allowed_areas` optionnel et `area_filter_dependency_policy` optionnel (`skip_blocked` \| `stop_on_cross_area_dependency`). |
| AREA-F-002 | `IssueRunAuthorizationGrant` DOIT valider l’intersection `work_unit_ids` × `allowed_areas` et rejeter toute WU hors aire ou `unknown`. |
| AREA-F-003 | `OpenRun` DOIT appliquer la même intersection ; une WU hors aire ne DOIT PAS ouvrir le Run. |
| AREA-F-004 | Le tick DOIT traiter comme non dispatchable toute WU du Run hors `allowed_areas`, avec raison `area_filter_mismatch`. |
| AREA-F-005 | Sous `skip_blocked`, une dépendance hors filtre NE DOIT PAS provoquer l’arrêt global tant qu’il reste du travail éligible indépendant. |
| AREA-F-006 | Sous `stop_on_cross_area_dependency`, le Run DOIT s’arrêter dès qu’une WU éligible n’est bloquée que par une dépendance hors filtre. |
| AREA-F-007 | Le filtre d’aire NE DOIT PAS restreindre les rôles de staffing/QA/revue autrement que via les règles `zone.area` déjà en vigueur. |
| AREA-F-008 | L’absence de `allowed_areas` DOIT préserver le comportement antérieur (sélection uniquement par `work_unit_ids`). |
| AREA-F-009 | Les skills / procédures d’émission de grant (mode nuit, runs planifiés) DOIVENT permettre de déclarer `allowed_areas` sans exiger que l’humain reconstitue manuellement la liste quand un sélecteur machine la dérive depuis le Project State — la liste résultante reste persistée dans `work_unit_ids`. |

## 5. Sélection assistée (DEVRAIT)

Lors de l’émission d’un grant avec `allowed_areas`, le Control Plane **DEVRAIT**
proposer de matérialiser `work_unit_ids` comme l’ensemble des Work Units
ready / planifiées dont `zone.area ∈ allowed_areas` (hors `unknown`), sous
plafond WIP et hors Work Units déjà couvertes par un autre Run actif. L’humain
reste l’autorité qui confirme le grant.

## 6. Hors périmètre

- Filtrer par chemin produit, risque, ou composant sans passer par `zone.area`
  (autres axes possibles ultérieurement).
- Remplacer le staffing dynamique par un « mode backend-only » au niveau profil.
- Réécrire `zone.area` a posteriori pour forcer l’éligibilité.

## 7. Références

- `distribution/payload/.ai-team/schemas/work-unit.schema.json` — `zone.area`
- `distribution/payload/.ai-team/schemas/run-authorization-grant.schema.json`
- `distribution/payload/.ai-team/constitution/60-staffing-policy.yaml`
- Document 6 (mode nuit, hors dépôt) §8 — RunAuthorizationGrant
- `docs/framework-design/requirements/mode-nuit-preuve-resilience-couverture.md`
- Document 28 — critères d’acceptation
