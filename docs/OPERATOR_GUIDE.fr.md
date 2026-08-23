# Guide opérateur

Ce guide détaille chaque étape. Pour le chemin rapide, voir le Quickstart de
`README.fr.md` — les deux se correspondent, ce guide donne juste plus de
contexte sur chaque étape.

## 0. Rappel : defaults vs exemples

`.cursor/` et `.ai-team/constitution/` sont des defaults prêts à l'emploi,
pas des exemples à effacer — voir `README.fr.md` pour le détail. Seuls
`.ai-team/project-profile.yaml` et `.ai-team/sources/source-registry.yaml`
sont vides et à remplir.

## 1. Installer le framework

Utiliser `tools/install.py`. Le framework est copié dans le repo projet sans supposer la stack technique. Le dossier `examples/` du framework n'est jamais copié.

## 2. Remplir la matière de construction

Placer les documents humains dans `docs/product/` puis compléter `.ai-team/sources/source-registry.yaml`. Un exemple commenté est déjà présent en haut du fichier.

Une source doit indiquer :

- son identifiant stable ;
- son chemin ou URI ;
- son autorité ;
- sa portée ;
- sa version ;
- son statut.

## 3. Compléter le profil projet

Le fichier `.ai-team/project-profile.yaml` contient les commandes techniques du projet : build, lint, tests, chemins source/tests/docs, environnement et règles de release. Un exemple commenté est en haut du fichier. C'est le seul autre fichier réellement vide — tout le reste de la Constitution est déjà un default fonctionnel.

## 4. Ouvrir le projet dans Cursor

Ouvrir le **projet installé** (pas ce dépôt framework) dans Cursor et faire confiance au workspace. Si une commande `/` n'apparaît pas tout de suite, redémarrer Cursor une fois — c'est ce qui déclenche la découverte de `.cursor/rules/`, `.cursor/agents/`, `.cursor/skills/` et `.cursor/hooks.json`.

## 5. Compiler avant de développer

Dans Cursor, invoquer explicitement le Skill (il n'est pas auto-déclenché) :

```text
/compile-project

Compile le projet à partir de @docs/product/. N'implémente aucun code
produit — arrête-toi après avoir produit le plan d'exécution pour mon
approbation.
```

Le Compiler doit produire ou mettre à jour :

- `.ai-team/state/project-state.yaml` ;
- `.ai-team/work-units/*.yaml` ;
- dépendances ;
- niveaux de risque ;
- vérifications requises ;
- plan de contexte ;
- staffing initial ;
- décisions manquantes.

Aucun code produit n'est modifié pendant cette étape.

## 6. Approuver G1

L'humain inspecte le plan. Il approuve, demande correction ou refuse. Une approbation est enregistrée dans `.ai-team/decisions/` et dans le Project State.

## 7. Activer l'orchestrateur

Utiliser le Skill `orchestrator` comme Custom Mode ou l'invoquer explicitement. Le Control Plane sélectionne uniquement les Work Units prêtes, dans les limites WIP.

## 8. Exécution

Pour chaque Work Unit :

1. construire un Context Package minimal ;
2. choisir le staffing ;
3. déléguer au Developer approprié ;
4. collecter le diff et les premières preuves ;
5. déclencher QA ;
6. déclencher Reviewer ;
7. déclencher Security si la politique l'impose ;
8. déclencher Auditor si la politique l'impose ;
9. produire la recette humaine ;
10. fermer seulement quand la Definition of Done est satisfaite.

## 9. Décision manquante

Une décision produit absente devient `DECISION_REQUEST`, jamais une supposition. Seules les Work Units dépendantes sont bloquées.

## 10. Release

Une release candidate lie un commit/ensemble de commits, migrations, preuves, reviews, findings ouverts et rollback plan. G3 protège la production.

## 11. Recette

Les agents préparent les scénarios. L'humain exécute et enregistre PASS / FAIL / PARTIAL. Un échec produit un Defect et une Work Unit de remédiation.
