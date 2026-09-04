# Document 6 — Catalogue des contrats de Rôle

**Statut** : version 1.2 corrigée (audit technique indépendant du 28 août 2026 appliqué : ligne `code-reviewer` corrigée §2). Le tableau sépare l’observation du dépôt et la cible du contrat publié.

## 1. Socle commun cible

Tout Rôle :

- reçoit uniquement les capacités déclarées dans sa révision ;
- n’écrit l’état de Gouvernance qu’au travers de commandes autorisées ;
- peut demander `record_observation` au travers d’un port médié, si l’Adaptateur sait préserver sa lecture seule produit ;
- reçoit un Context Package lorsque la Procédure l’exige ; cette lecture n’est pas présentée comme un comportement déjà explicite dans tous les fichiers Cursor ;
- retourne les identités du bundle, du Rôle, de la Procédure et du commit observé.

## 2. Catalogue

| RoleId | Mandat | Écriture produit | Écriture Gouvernance autoritaire | Procédures explicitement observées dans Cursor |
|---|---|---|---|---|
| `backend-developer` | Implémenter les Work Units backend dans leur scope. | `scoped` | Aucune | Aucune référence explicite supplémentaire. |
| `frontend-developer` | Implémenter UI, état et interactions avec preuve visuelle. | `scoped` | Aucune | `frontend-design`, `webapp-testing`. |
| `qa-test` | Vérifier indépendamment un SHA stable et produire/corriger des tests. | `tests_only` | Aucune | `webapp-testing`. |
| `code-reviewer` | Examiner diff, contrats, maintenabilité et risques. | `none` | Aucune | `webapp-testing` (référencé pour vérifier qu'une preuve visuelle existe déjà ; le Reviewer ne l'exécute pas lui-même, il est read-only). |
| `security-reviewer` | Examiner authentification, autorisation, secrets, injections et frontières de confiance. | `none` | Aucune | Aucune référence explicite supplémentaire. |
| `auditor` | Reconstruire les faits et mesurer la conformité sans remédier pendant la mesure. | `none` | Aucune | Aucune référence explicite supplémentaire. |
| `release-agent` | Préparer un candidat, ses preuves, migrations et rollback sans autoriser G3. | `none` | Aucune | Aucune référence explicite supplémentaire. |
| `architect` | Analyser architecture, contrats et impact ; proposer sans autorité produit. | `none` | Aucune | Aucune référence explicite supplémentaire. |
| `product-analyst` | Structurer le matériau produit humain sans arbitrer les conflits d’autorité. | `none` | Aucune | Aucune référence explicite supplémentaire. |
| `reconciliation-steward` | Comparer l’existant à l’intention et appliquer uniquement les actions de convergence pré-compilation explicitement approuvées. | `scoped` | Aucune | `reconcile-project`. |

Le Control Plane est défini au Document 5. Pour tous les Rôles délégués, `record_observation` est une capacité **cible médiée**, pas une capacité actuellement observée dans leur frontmatter.

## 3. Traduction Cursor actuelle

- Les rôles à écriture produit ou tests, dont `reconciliation-steward`, ont `readonly: false`.
- Les six autres Rôles métier ci-dessus ont `readonly: true`.
- Cursor interprète `readonly` comme une restriction d’écriture de fichiers et de commandes à changement d’état, pas seulement comme « lecture seule produit ».
- Le futur Adaptateur doit donc offrir `record_observation` sans élargir arbitrairement l’écriture de ces Rôles.

## 4. Exclusion de `auth-smoke`

`auth-smoke` est une sonde propre à l’Adaptateur Cursor qui teste le routage de l’allowlist CLI. Il n’incarne pas un mandat de Gouvernance et n’entre pas dans le Published Contract Bundle métier.

## 5. Limites

- Les procédures accessibles sont déduites des références textuelles ; le dépôt Cursor n’a pas de champ de liste de skills dans ses agents.
- Une absence dans la dernière colonne ne prouve pas une interdiction.
- Le catalogue cible doit encore recevoir des révisions/hashes et être validé atomiquement avec le catalogue des Procédures.

## 6. Traceabilité bundle v1 (WU-P2-ROLES, WU-P2-PROCEDURES)

Les quinze `RoleDefinitionRevision` agnostiques, dont `control-plane` et `reconciliation-steward`, sont transcrits sous `src/governed_ai/contracts/bundles/v1/roles/`. Les dix-huit `ProcedureRevision` référencées par ces rôles sont transcrites sous `src/governed_ai/contracts/bundles/v1/procedures/` (révision `1.0.0`, contenu agnostique complet). Les étapes propres à l'Adaptateur Cursor sont documentées hors manifeste dans `adapters/cursor/compiler-notes.yaml`. `auth-smoke` reste exclu (§4). Le manifeste `bundles/v1/manifest.json` assemble rôles et procédures pour validation atomique.

## Sources

Les dix fichiers sous `.cursor/agents/` et les skills sous `.cursor/skills/`.
