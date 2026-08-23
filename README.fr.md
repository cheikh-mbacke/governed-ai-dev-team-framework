# Framework d'équipe IA de développement gouvernée

*[Read in English](README.md)*

Ce framework transforme Cursor en une petite équipe d'agents IA gouvernée. Des subagents spécialisés — développeur, reviewer, security reviewer, auditeur — travaillent sur des tâches bien délimitées, selon des règles versionnées dans les fichiers du dépôt, pas dans un unique prompt géant que personne ne relit.

Rien n'est marqué terminé sans preuve : tests réellement exécutés, review effectuée, audit indépendant quand le risque l'exige. Les décisions produit et les mises en production restent entre les mains d'un humain, à des points de validation explicites (les « gates ») que l'IA ne peut pas contourner.

## Principe de fonctionnement

Le framework sépare :

1. **Matière humaine de construction** — ce qui doit être construit : intention produit, périmètre, règles métier, exigences, architecture, contraintes, critères d'acceptation.
2. **Constitution d'ingénierie** — comment l'organisation IA a le droit de fonctionner : autorité, décomposition, contexte, staffing, permissions, tests, review, audit, release et gates humaines.
3. **État d'exécution** — le modèle runtime dérivé et inspectable : Project State, Work Units, dépendances, preuves, findings, décisions, release candidates et résultats de recette.

L'équipe IA peut analyser, proposer, implémenter, tester, reviewer et auditer. Elle ne peut **jamais inventer silencieusement une décision produit manquante, ni modifier sa propre Constitution**.

## Ce qui est déjà implémenté dans ce dépôt

- Project Rules Cursor dans `.cursor/rules/`
- Subagents Cursor personnalisés dans `.cursor/agents/`
- Agent Skills Cursor dans `.cursor/skills/`
- Hooks de projet Cursor dans `.cursor/hooks.json`
- Règles d'exécution Cursor par dépôt dans `.cursor/permissions.json`
- Règles Bugbot Cursor dans `.cursor/BUGBOT.md`
- Constitution d'ingénierie dans `.ai-team/constitution/`
- JSON Schemas pour tous les objets d'état dans `.ai-team/schemas/`
- Templates prêts à l'emploi dans `.ai-team/templates/`
- Dossiers runtime pour Work Units, décisions, preuves, findings, audit, release et recette
- Outillage de validation et de statut dans `scripts/ai-team/`
- Installeur multiplateforme dans `tools/install.py`
- Un exemple de référence optionnel, non installé, dans `examples/project-a/`

## Prérequis

- **Python 3.10 ou supérieur**, disponible dans ton PATH.
- Avant d'installer, lance `python --version`. Si cette commande n'est pas trouvée, essaie `python3 --version` à la place.
  - Si seule `python3` fonctionne sur ta machine — cas fréquent sur macOS
    et sur les distributions Linux qui ne fournissent pas de commande
    `python` nue — remplace `python` par `python3` dans toutes les
    commandes de ce guide, **et** dans `.cursor/hooks.json` : Cursor exécute
    la chaîne `command` de chaque hook directement dans le shell de ton
    système d'exploitation, avec le nom d'interpréteur exact écrit
    là-dedans, donc les hooks ont besoin de celui qui correspond réellement
    à Python 3 sur ta machine.
- Cursor, avec ton projet cible ouvert en tant que **workspace de confiance**
  (« trusted workspace », voir l'étape 3 ci-dessous).

## Quickstart

### 1. Installer dans ton projet

Clone ce framework où tu veux, puis lance l'installeur une fois contre ton
dépôt cible. Remplace `/chemin/vers/ton/projet`, `ton-id-de-projet` et
`"Nom De Ton Projet"` ci-dessous par les vraies valeurs de ton projet — ce
ne sont pas des valeurs à garder telles quelles :

```bash
python tools/install.py --target /chemin/vers/ton/projet --project-id ton-id-de-projet --project-name "Nom De Ton Projet"
```

Cette commande est volontairement écrite sur une seule ligne pour pouvoir
être collée telle quelle dans n'importe quel shell. Si tu la répartis
toi-même sur plusieurs lignes, note que le caractère de continuation de
ligne diffère selon le shell : `\` sur bash/zsh/Git Bash, `^` sur
`cmd.exe` (Windows), `` ` `` sur PowerShell.

`install.py` n'écrase jamais un fichier déjà présent dans la cible (sauf
`--force`), et ne copie jamais `examples/`.

### 2. Remplir ce que toi seul sais

Deux fichiers sous `.ai-team/` sont réellement vides et ont besoin de
vraies valeurs avant de compiler quoi que ce soit. Tout le reste de la
Constitution est déjà un default fonctionnel — tu n'as besoin d'avoir lu
aucun document de conception externe pour comprendre ce qui va dans ces
deux fichiers.

**`.ai-team/project-profile.yaml`** — ouvre-le et remplace les valeurs
placeholder. Un exemple commenté est en haut du fichier ; concrètement, un
profil rempli ressemble à ceci :

```yaml
project:
  id: checkout-service
  name: Checkout Service
paths:
  source_roots: [src]
  test_roots: [tests]
commands:
  build: "npm run build"
  lint: "npm run lint"
  unit_test: "npm test"
human_authorities:
  product: alice
  engineering_constitution: alice
  production_release: bob
  final_acceptance: alice
```

- `commands` sont les commandes shell exactes que les subagents Developer
  vont exécuter pour builder, linter et tester ton projet. Si ton projet
  n'a pas d'étape de build, laisse cette entrée à `null` — c'est normal.
- `human_authorities` ne sont pas des rôles à remplir pour l'IA ; ce sont
  les vrais noms des personnes qui ont le dernier mot à chacune des gates
  humaines du framework (voir « Déroulé runtime » ci-dessous) : qui peut
  changer le périmètre produit, qui peut changer la Constitution
  d'ingénierie elle-même, qui peut autoriser une release en production, et
  qui signe la recette finale. Sur un petit projet, ça peut être le même
  nom quatre fois. Le framework citera ces personnes chaque fois qu'il a
  besoin de demander une décision à un humain.

**`.ai-team/sources/source-registry.yaml`** — une entrée par document qui
définit réellement ce que tu construis (exigences, specs, règles métier...).
Un exemple commenté est en haut du fichier ; concrètement, si tu déposes un
fichier à `docs/product/requirements.md`, enregistre-le ainsi :

```yaml
sources:
  - id: requirements-v1
    type: human_construction_material
    path: docs/product/requirements.md
    authority: human
    scope: project
    version: "1.0"
    status: active
    owner: product
```

Tout document produit que tu n'enregistres pas ici est invisible pour le
framework : les agents IA ne traitent comme autoritatives que les sources
explicitement listées.

Puis vérifie ce qu'il reste, s'il reste quelque chose, à compléter :

```bash
python scripts/ai-team/validate.py
```

Ce script ne signale que ces deux fichiers (et, plus tard, les Work Units
que tu crées) — il ne te demande jamais de toucher aux defaults de la
Constitution.

### 3. Ouvrir le projet dans Cursor

Ouvre le projet installé (pas ce dépôt framework) dans Cursor, en faisant
confiance au workspace. Cursor découvre `.cursor/rules/`, `.cursor/agents/`,
`.cursor/skills/` et `.cursor/hooks.json` à l'ouverture ; si une commande
`/` attendue n'apparaît pas, redémarre Cursor une fois.

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
limites WIP ci-dessous — jamais tous en même temps.

Envie de voir à quoi ressemble une Work Unit déjà compilée avant de lancer
la tienne ? Regarde `examples/project-a/` — référence en lecture seule,
jamais installée, rien à nettoyer.

## Profil par défaut recommandé

Ce dépôt fournit un **profil de référence assumé** :

- Autonomie : niveau 2 — équipe semi-autonome
- Work Units actives max : 3
- Workers écrivant du code en parallèle max : 2
- Work Units risque élevé/critique simultanées max : 1
- Un writer principal par Work Unit
- Reviewer : lecture seule
- Security reviewer : lecture seule
- Auditor : lecture seule et indépendant de la remédiation
- Release production : gate humaine G3
- Recette finale : gate humaine G4

Ce sont des defaults d'implémentation, pas des vérités universelles. Change-les dans la Constitution et versionne le changement.

## Déroulé runtime

```text
Matière produit humaine + Constitution d'ingénierie
                    |
                    v
               Readiness G0
                    |
                    v
              Project Compiler
                    |
                    v
      Project State + Work Units + plan
                    |
                    v
           Approbation humaine G1
                    |
                    v
               Orchestrateur
        +-----------+-----------+
        |           |           |
     Developer      QA       Reviewer
        |           |           |
        +-----------+-----------+
                    |
                    v
             Audit indépendant
                    |
                    v
          Release Candidate / G3
                    |
                    v
            Recette humaine G4
                    |
                    v
                   Done
```

## Note de sécurité importante

Les règles Cursor, les prompts, les hooks et `permissions.json` sont des **contrôles de gouvernance, pas une frontière de sécurité complète**. Garde la protection de branche, les checks CI requis, la protection des environnements, les secrets, les credentials de déploiement, CODEOWNERS et l'IAM production en dehors du modèle, et fais-les respecter par ton hébergeur Git / CI / infrastructure cloud.

Si Cursor arrête soudainement de pouvoir exécuter *n'importe quelle*
commande shell juste après l'ouverture du projet, vérifie d'abord la
section Prérequis ci-dessus : le hook `beforeShellExecution` échoue en
mode fermé par conception (voir `.cursor/hooks.json`), donc un interpréteur
Python qui ne correspond pas exactement au nom de commande écrit là-dedans
bloque les commandes au lieu de simplement ignorer le contrôle.

Voir `docs/SECURITY_MODEL.md`.

## Pour aller plus loin

- Checklist complète avant un vrai projet : `docs/ADOPTER_CHECKLIST.md`.
- Guide opérateur pas à pas (en français) : `docs/OPERATOR_GUIDE.fr.md`.
- Architecture, machine à états et pipeline de review : `docs/ARCHITECTURE.md`.
- Ce que couvrent (et ne couvrent pas) les contrôles Cursor : `docs/SECURITY_MODEL.md`.
- Correspondance entre ce dépôt et le document de cadrage de base : `docs/SOURCE_MAPPING.md`.

## Licence

MIT. Voir `LICENSE`.
