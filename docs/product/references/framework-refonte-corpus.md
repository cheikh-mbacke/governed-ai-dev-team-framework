# Corpus DDD corrigé — governed-ai-dev-team-framework

Cette édition révise les Documents 00 à 10 après audit indépendant du dépôt à la révision `9f77085eb2fc7a1f372556e9ad2714cf5318bd98`.

## Règles éditoriales appliquées

- séparation entre **observé**, **règle déjà imposée** et **cible** ;
- aucune immutabilité, transition ou frontière transactionnelle déduite d’un schéma seul ;
- distinction entre sous-domaine et Bounded Context ;
- patterns DDD nommés seulement lorsque direction, rôle amont/aval et mécanisme sont cohérents ;
- matrices d’outils datées et fondées sur leurs documentations officielles actuelles ;
- section Limites dans chaque document.

## Corrections transversales

| Sujet | Correction |
|---|---|
| Capacité d’écriture | Trois axes cohérents dans les Documents 3, 5 et 6. |
| Rôle/Procédure | Identités stables séparées de révisions immuables ; propriété attribuée à Gouvernance. |
| Catalogues | Remplacés par un `PublishedContractBundle` atomique. |
| Interaction | La sortie brute peut être lue mais ne peut pas, seule, autoriser une transition. |
| StructuredEvent | Reclassé comme mélange actuel à séparer en Event, Request/Command et Workflow Message. |
| Gate Decision | Décrit comme journal auxiliaire non transactionnel ; cible append-only/rejouable ou source de vérité explicitement différente. |
| Adaptateur | `AdapterRelease` valeur, Runtime composant/service, `AdapterInstallation` candidate Entité. |
| Distribution | `managed_files` et timestamps conservés ; direction Adaptateur → Distribution corrigée. |
| Feedback | Mutations non implémentées reconnues ; export persistant et consentement cible explicités. |
| Codex | Hooks et skills par agent reconnus selon la documentation actuelle. |

## Emplacement dans `docs/product/`

| Doc | Titre | Catégorie | Fichier |
|---|---|---|---|
| 00 | Vision et objectifs | `vision-and-scope/` | [`00-vision-et-objectifs.md`](../vision-and-scope/00-vision-et-objectifs.md) |
| 01 | Langage ubiquitaire | `users-and-rules/` | [`01-langage-ubiquitaire.md`](../users-and-rules/01-langage-ubiquitaire.md) |
| 02 | Carte des contextes | `architecture-and-constraints/` | [`02-carte-des-contextes.md`](../architecture-and-constraints/02-carte-des-contextes.md) |
| 03 | Modèle tactique Adaptateur/Runtime | `architecture-and-constraints/` | [`03-modele-tactique-adaptateur-runtime.md`](../architecture-and-constraints/03-modele-tactique-adaptateur-runtime.md) |
| 04 | Protocole d’interaction noyau ↔ Adaptateur | `requirements/` | [`04-protocole-interaction.md`](../requirements/04-protocole-interaction.md) |
| 05 | Résolution des écarts du protocole | `requirements/` | [`05-combler-ecarts-protocole.md`](../requirements/05-combler-ecarts-protocole.md) |
| 06 | Catalogue des contrats de Rôle | `users-and-rules/` | [`06-catalogue-contrats-role.md`](../users-and-rules/06-catalogue-contrats-role.md) |
| 07 | Modèle tactique Gouvernance | `architecture-and-constraints/` | [`07-modele-tactique-gouvernance.md`](../architecture-and-constraints/07-modele-tactique-gouvernance.md) |
| 08 | Classification Rôle, Procédure et Adaptateur | `architecture-and-constraints/` | [`08-classification-role-procedure.md`](../architecture-and-constraints/08-classification-role-procedure.md) |
| 09 | Modèle tactique Distribution/Installation | `architecture-and-constraints/` | [`09-modele-tactique-distribution.md`](../architecture-and-constraints/09-modele-tactique-distribution.md) |
| 10 | Modèle tactique Feedback/Apprentissage | `architecture-and-constraints/` | [`10-modele-tactique-feedback.md`](../architecture-and-constraints/10-modele-tactique-feedback.md) |
| 11 | Architecture cible | `architecture-and-constraints/` | [`11-architecture-cible.md`](../architecture-and-constraints/11-architecture-cible.md) |
| 12 | Contrats noyau ↔ Adaptateur | `architecture-and-constraints/` | [`12-contrats-noyau-adaptateur.md`](../architecture-and-constraints/12-contrats-noyau-adaptateur.md) |
| 13 | Plan de migration | `architecture-and-constraints/` | [`13-plan-de-migration.md`](../architecture-and-constraints/13-plan-de-migration.md) |
| 14 | Tests de conformité | `acceptance-criteria/` | [`14-tests-de-conformite.md`](../acceptance-criteria/14-tests-de-conformite.md) |

## Ordre de lecture

00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10, puis les spécifications techniques 11 → 14 (voir tableau ci-dessus).

Le rapport d’audit d’origine reste disponible à la racine du dépôt sous `rapport-audit-ddd-governed-ai.md` s’il y est ajouté.

## Corrections post-audit technique indépendant (28 août 2026, portant sur 00–14)

Un second audit indépendant, portant cette fois sur l’ensemble 00–14 (y compris les spécifications techniques 11–14 ajoutées depuis la première édition de ce corpus) et sur le dépôt réel à la révision `981bf43c1c0cbabfd729e8e410ed288c12ce8ca9` (arbre identique à `9f77085`, aucune dérive), a confirmé la quasi-totalité des affirmations de ce corpus et identifié un petit nombre de corrections localisées, toutes appliquées dans cette édition :

| ID | Document(s) corrigé(s) | Nature | Correction appliquée |
|---|---|---|---|
| BLK-01 | 03 §1, 12 §2.2 | Noms de champs `RoleDefinitionRevision` non harmonisés entre le modèle tactique (03) et le contrat technique (12) | Note ajoutée au Document 03 désignant le Document 12 comme seule autorité de format de fil. |
| BLK-02 | 12 §7 | `human_authorization` exigée (11 §8) et testée (14, CG-007/CG-008) sans forme technique définie | Sous-section 7.1 ajoutée au Document 12 : forme JSON, invariant de non-réutilisation, code d’erreur associé. |
| ERR-01 | 06 §2 | Ligne `code-reviewer` niait à tort toute référence de skill, alors que `.cursor/agents/code-reviewer.md` référence `webapp-testing/SKILL.md` | Cellule corrigée avec la nuance vérification/production de preuve. |
| ERR-02 | 12 §3.1 | Identité Adaptateur représentée différemment dans le Descriptor (champs plats) et dans ExecutionRequest/RuntimeResult (objet imbriqué) | Note de cohérence ajoutée expliquant et figeant les deux formes. |
| ERR-03 | 12 §10 | Aucun exemple JSON pour Request et Workflow Message, alors que leur séparation d’avec Domain Event est un résultat central des Documents 04/07 | Sous-sections 10.1 (Request) et 10.2 (Workflow Message) ajoutées avec exemples minimaux. |
| RES-01 | 11 §7.3, 14 §7 | Aucun failpoint nommé pour une écriture de journal interrompue **pendant** l’écriture (distinct d’un journal falsifié après coup) | Précision ajoutée au Document 11 ; test TX-009 ajouté au Document 14. |
| RES-02 | 13 §7 | Comportement non spécifié si la traduction wrapper legacy → Command Envelope échoue elle-même | Règle ajoutée : arrêt avant tout appel au Gateway, jamais de repli silencieux sur l’écriture directe. |
| — | 14 §6, §10bis | Deux obligations normatives (préconditions G4 ; anti-invention de données en migration d’objets mutables) couvertes seulement en prose, sans identifiant de test dédié | Ajout de SM-001/SM-002 et MIG-001/MIG-002. |

Aucune correction n’a modifié une décision structurante déjà prise par ce corpus ; toutes sont des clarifications ou des compléments localisés. Le rapport d’audit correspondant liste également les points jugés non bloquants (améliorations F.4), volontairement non appliqués ici car ils ne modifient aucun document — ils concernent des vérifications à mener (ex. capacités Codex `skills.config`/`mcp_servers`) ou des exécutions à réaliser (ex. migration réelle sur projet témoin), pas du texte à corriger.
