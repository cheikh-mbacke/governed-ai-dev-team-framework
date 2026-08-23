# Framework d'équipe IA de développement gouvernée

*[Read in English](README.md)*

Un framework prêt à mettre sur GitHub pour intégrer dans un projet une **équipe d'agents IA gouvernée par l'humain avec Cursor**.

L'idée n'est pas de fournir un gros prompt. Le dépôt matérialise l'organisation sous forme de fichiers versionnés : Constitution d'ingénierie, rôles, staffing, permissions, Work Units, Project State, preuves, review, audit indépendant et gates humaines.

## Quickstart

### 1. Installer dans ton projet

```bash
python tools/install.py \
  --target /chemin/vers/projet-a \
  --project-id projet-a \
  --project-name "Projet A"
```

`install.py` n'écrase jamais un fichier déjà présent dans la cible (sauf
`--force`), et ne copie jamais
`examples/`.

### 2. Remplir ce que toi seul sais

Deux fichiers sous `.ai-team/` ont besoin de vraies valeurs avant de
compiler — tout le reste est déjà utilisable tel quel :

- **`.ai-team/project-profile.yaml`** — tes vraies commandes build/lint/test,
  chemins source/tests, et qui détient l'autorité produit / Constitution /
  release / recette sur ce projet. Un exemple commenté est en haut du
  fichier.
- **`.ai-team/sources/source-registry.yaml`** — une entrée par document
  produit autoritatif que tu vas déposer sous `docs/product/`. Même
  logique : exemple commenté en haut du fichier.

Puis vérifie ce qu'il reste à compléter :

```bash
python scripts/ai-team/validate.py
```

Ce script ne signale que ces deux fichiers (et les Work Units créées
ensuite) — il ne te demande jamais de toucher aux defaults de la
Constitution.

### 3. Ouvrir le projet dans Cursor

Ouvre le projet installé (pas ce dépôt framework) dans Cursor, en faisant
confiance au workspace ("trust workspace"). Cursor découvre `.cursor/rules/`,
`.cursor/agents/`, `.cursor/skills/` et `.cursor/hooks.json` à l'ouverture ;
si une commande `/` attendue n'apparaît pas, redémarre Cursor une fois.

### 4. Compiler le projet

Dans l'agent Cursor, invoque explicitement le Skill — il n'est
volontairement pas auto-déclenché, donc ouvrir Cursor ne lance jamais
l'équipe silencieusement :

```text
/compile-project

Compile le projet à partir de @docs/product/. N'implémente aucun code
produit — arrête-toi après avoir produit le plan d'exécution pour mon
approbation.
```

Cela lit les sources enregistrées et la Constitution, puis produit (ou met à
jour) `.ai-team/state/project-state.yaml` et `.ai-team/work-units/*.yaml` —
graphe de dépendances, niveaux de risque, vérifications requises, plan de
contexte et proposition de staffing. Aucun code produit n'est touché.

### 5. Inspecter et approuver G1

```bash
python scripts/ai-team/status.py
```

Relis les Work Units et le staffing proposés. Une fois satisfait :

```bash
python scripts/ai-team/record_gate.py G1 approved --by TON_NOM --note "Plan d'exécution approuvé"
```

### 6. Démarrer l'orchestrateur

```text
/orchestrator
```

Utilise-le comme Custom Mode pour le garder actif pendant la session. Il
n'active les subagents spécialisés que pour les Work Units prêtes, dans les
limites WIP par défaut — jamais tous en même temps.

Envie de voir à quoi ressemble une Work Unit déjà compilée avant de lancer
la tienne ? Regarde `examples/project-a/` — référence en lecture seule,
jamais installée, rien à nettoyer.

## Profil par défaut recommandé

- Autonomie : niveau 2 — équipe semi-autonome
- Work Units actives max : 3
- Workers écrivant du code en parallèle max : 2
- Work Units risque élevé/critique simultanées max : 1
- Un writer principal par Work Unit
- Reviewer, Security Reviewer, Auditor : lecture seule
- Release production : gate humaine G3
- Recette finale : gate humaine G4

Ce sont des defaults d'implémentation, pas des vérités universelles. Change-les dans la Constitution et versionne le changement.

## Pour aller plus loin

- Checklist complète avant un vrai projet : `docs/ADOPTER_CHECKLIST.md`.
- Guide opérateur pas à pas (en français) : `docs/OPERATOR_GUIDE.fr.md`.
- Architecture, machine à états et pipeline de review : `docs/ARCHITECTURE.md`.
- Ce que couvrent (et ne couvrent pas) les contrôles Cursor : `docs/SECURITY_MODEL.md`.
- Correspondance entre ce dépôt et le document de cadrage de base : `docs/SOURCE_MAPPING.md`.

## Licence

MIT. Voir `LICENSE`.
