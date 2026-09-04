# Document 21 — Réconciliation pré-compilation

**Statut** : version 1.0 — exigence normative.

Les termes **DOIT**, **NE DOIT PAS**, **DEVRAIT** et **PEUT** expriment une
obligation, une interdiction, une recommandation forte et une option.

## 1. Problème

Sur un projet avancé, le dépôt contient une réalité construite avant l’adoption du
framework. Cette réalité peut être cohérente, hors périmètre, obsolète, incomplète
ou contradictoire avec l’intention humaine. La compilation directe transformerait
alors des observations techniques en plan autoritaire sans arbitrage explicite.

L’assessment d’adoption (Documents 19–20) révèle ce coût avant installation, mais
ne réalise pas la convergence post-installation. Une commande séparée est donc
requise entre installation et `/compile-project`.

## 2. Séquence obligatoire

```text
Assessment → Décision d’adoption → Installation → /reconcile-project
                                                   ↓
                                      baseline cohérente et empreintée
                                                   ↓
                                           /compile-project
```

`/reconcile-project` est une procédure post-installation et pré-G0. Elle ne crée
pas de Work Units et ne compile pas le projet. `/compile-project` DOIT refuser une
baseline absente, incomplète ou obsolète.

## 3. Exigences fonctionnelles

| ID | Exigence |
|---|---|
| REC-F-001 | La commande DOIT recueillir, pour le périmètre demandé, objectifs, utilisateurs, règles métier, contraintes, hors-scope, décisions antérieures et critères d’acceptation. |
| REC-F-002 | Chaque matière déclarée suffisante DOIT référencer, par son identifiant de registre, au moins une source humaine autoritaire active et résoluble. |
| REC-F-003 | La commande DOIT inventorier le code, l’architecture, les tests, les données/migrations, les dépendances, la documentation, l’infrastructure et la dette pertinents. |
| REC-F-004 | Le dépôt DOIT rester une réalité observée ; son comportement ne DOIT PAS devenir une intention produit par inférence silencieuse. |
| REC-F-005 | Chaque surface matérielle DOIT être classée `conformant`, `adapt`, `obsolete_out_of_scope`, `conflicting` ou `undetermined`. |
| REC-F-006 | Chaque surface DOIT recevoir une action explicite `keep`, `migrate`, `rewrite`, `isolate`, `delete` ou `clarify`. |
| REC-F-007 | Toute ambiguïté ou contradiction non résolue DOIT bloquer la baseline et produire une demande de décision humaine. |
| REC-F-008 | Les actions `migrate`, `rewrite`, `isolate` et `delete` NE DOIVENT PAS être appliquées sans référence d’approbation humaine explicite. |
| REC-F-009 | La commande PEUT appliquer les actions approuvées, mais seulement dans le périmètre déclaré et avec preuve de résultat. |
| REC-F-010 | Les vérifications requises non exécutées ou en échec DOIVENT rester bloquantes. |
| REC-F-011 | La sortie DOIT être un manifeste machine-lisible validé par schéma, lié au même `project_id` que le profil, et dont l’état `ready` n’est produit que par le finaliseur. Chaque résolution et waiver humain doit conserver sa référence de décision. |
| REC-F-012 | Le finaliseur DOIT calculer une empreinte déterministe des contenus project-owned, en excluant le payload géré et le manifeste de réconciliation lui-même. |
| REC-F-013 | Toute modification ultérieure du contenu project-owned DOIT invalider l’autorisation de compiler jusqu’à nouvelle réconciliation. |
| REC-F-014 | `/compile-project` DOIT exécuter le contrôle machine de la baseline avant toute production de plan ou de Work Unit. |

## 4. Manifeste

Le manifeste canonique est
`.ai-team/reconciliation/baseline.yaml`, validé par
`.ai-team/schemas/reconciliation.schema.json`. Il contient :

- le périmètre inclus/exclu ;
- l’évaluation de la matière humaine et ses références ;
- l’inventaire as-built ;
- la matrice de convergence ;
- les décisions et approbations ;
- les résultats de vérification ;
- l’empreinte de baseline.

États : `draft`, `awaiting_decisions`, `approved`, `applying`, `blocked`,
`ready`, `stale`.

## 5. Sécurité des mutations

L’invocation de `/reconcile-project` autorise l’analyse et la création du rapport.
Elle n’autorise pas implicitement une suppression, une réécriture ou une migration.
Le plan complet doit être présenté, puis chaque action sensible doit porter une
référence d’approbation humaine. Les changements doivent rester récupérables par
l’historique du dépôt ou une sauvegarde explicite.

## 6. Limites

- L’inventaire initial automatique est structurel ; la comparaison sémantique avec
  l’intention reste conduite par l’agent et arbitrée par l’humain.
- L’empreinte détecte la dérive de contenu, pas la validité métier d’une décision.
- Une baseline cohérente ne vaut ni G1, ni preuve de livraison, ni acceptation G4.

## Références

- Document 19 — Gouvernance exclusive et assessment d’adoption
- Document 22 — Conformité de la réconciliation pré-compilation
- [Réconciliation d’un projet existant](../../adopter-guide/project-reconciliation.md)
