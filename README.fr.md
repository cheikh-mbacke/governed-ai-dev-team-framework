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

### 1. Récupérer le framework et l'installer dans ton projet

```bash
git clone https://github.com/cheikh-mbacke/governed-ai-dev-team-framework.git
cd governed-ai-dev-team-framework
```

Lance l'installeur **depuis l'intérieur de ce dossier cloné** —
`tools/install.py` est un chemin relatif à ce dossier, pas à ton projet ni
à l'endroit où se trouve ton terminal. Remplace `/chemin/vers/ton/projet`,
`ton-id-de-projet` et `"Nom De Ton Projet"` ci-dessous par tes vraies
valeurs :

```bash
python tools/install.py --target /chemin/vers/ton/projet --project-id ton-id-de-projet --project-name "Nom De Ton Projet"
```

Tu préfères lancer ça depuis ailleurs ? Donne le chemin complet vers le
script, par ex. `python ~/governed-ai-dev-team-framework/tools/install.py ...`.

Écrite sur une seule ligne exprès, pour être collée telle quelle dans
n'importe quel shell. Si tu la répartis toi-même sur plusieurs lignes, le
caractère de continuation diffère selon le shell : `\` sur bash/zsh/Git
Bash, `^` sur `cmd.exe`, `` ` `` sur PowerShell.

`install.py` n'écrase jamais un fichier déjà présent dans la cible (sauf
`--force`), et ne copie jamais `examples/`.

### 2. Remplir ce que toi seul sais

Deux fichiers sous `.ai-team/` sont vides et ont besoin de vraies valeurs
avant de compiler quoi que ce soit. Tout le reste de la Constitution est
déjà prêt à l'emploi — pas besoin d'avoir lu de document de conception
externe pour comprendre ce qui va dans ces deux fichiers.

**`.ai-team/sources/source-registry.yaml`** — une entrée par document qui
définit ce que tu construis. L'installeur a déjà créé sept sous-dossiers
de catégorie sous `docs/product/` — `vision-and-scope/`, `users-and-rules/`,
`requirements/`, `acceptance-criteria/`, `architecture-and-constraints/`,
`security-and-compliance/`, `references/` — chacun avec un court README
(voir `docs/product/README.md`). Les utiliser est optionnel ; un simple
fichier à plat fonctionne tout aussi bien. Un exemple commenté est en haut
du fichier de registre ; concrètement, déposer un fichier à
`docs/product/requirements/requirements.md` s'enregistre ainsi :

```yaml
sources:
  - id: requirements-v1
    type: human_construction_material
    path: docs/product/requirements/requirements.md
    authority: human
    scope: requirements
    version: "1.0"
    status: active
    owner: product
```

Un document non enregistré est invisible pour le framework : les agents ne
traitent comme autoritatives que les sources explicitement listées ici.

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
  exécutent pour builder, linter et tester ton projet. Pas d'étape de
  build ? Laisse `null`.
- `human_authorities` ne sont pas des rôles pour l'IA — ce sont les vrais
  noms des personnes qui ont le dernier mot à chaque gate humaine (voir
  « Déroulé runtime » ci-dessous) : qui peut changer le périmètre produit,
  qui peut changer la Constitution elle-même, qui autorise une release en
  production, qui signe la recette finale. Le même nom quatre fois, c'est
  très bien sur un petit projet. Le framework cite ces personnes chaque
  fois qu'il a besoin d'une décision humaine.

Tu préfères ne pas les remplir à la main ? Une fois le projet ouvert dans
Cursor (étape 3), invoque `/propose-profile` à la place : il inspecte ton
dépôt et `docs/product/` à la recherche de signaux concrets déjà présents
— un script dans `package.json`, un `Cargo.toml`, des fichiers déposés
dans les dossiers de catégorie — et propose des valeurs pour les deux
fichiers ci-dessus. Il n'écrit jamais rien avant que tu confirmes, et ne
devine jamais tes approbateurs humains ; il te le demande toujours
directement.

Puis vérifie ce qu'il reste à compléter :

```bash
python scripts/ai-team/validate.py
```

Il vérifie ces deux fichiers et affiche un avertissement par manque — par
exemple `WARN Project command 'build' is not configured`, ou
`WARN No authoritative product sources are registered`. Corrige, relance,
répète jusqu'à ce que les deux soient sans avertissement. (Il commence
aussi à faire des rapports sur les Work Units une fois que tu en crées à
l'étape 4 — normal, pas un problème avec ta configuration.) Il ne te
demande jamais de toucher `.ai-team/constitution/` — c'est déjà complet.

### 3. Ouvrir le projet dans Cursor

Ouvre **le dossier de ton projet** — celui dans lequel tu as installé le
framework à l'étape 1, pas le dépôt framework que tu as cloné — dans
Cursor (File → Open Folder). À la première ouverture, Cursor affiche
généralement une invite demandant si tu fais confiance aux auteurs du
dossier (« Trust this folder » / workspace de confiance) ; accepte-la —
c'est ce qui permet à Cursor de lire les fichiers `.cursor/` qu'on vient
d'installer (règles, agents, skills, hooks) et de les activer. Si une
commande `/` attendue (comme `/compile-project`) n'apparaît pas quand tu
tapes `/` dans le chat, ferme et rouvre Cursor une fois — ça suffit
généralement à forcer la redécouverte.

### 4. Compiler le projet

Dans n'importe quelle session de chat Cursor Agent normale — rien de
spécial à sélectionner avant — invoque explicitement le Skill. Il n'est
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

Ce script affiche un résumé lisible de ce que `/compile-project` vient de
produire : la phase actuelle, le statut de chaque gate (G0 à G4), combien
de Work Units existent et leur statut, et les décisions ou defects encore
ouverts. C'est un raccourci pour ne pas avoir à ouvrir chaque fichier sous
`.ai-team/state/` et `.ai-team/work-units/` à la main — tu peux tout aussi
bien les lire directement si tu préfères.

Relis les Work Units et le staffing proposés. Une fois satisfait :

```bash
python scripts/ai-team/record_gate.py G1 approved --by TON_NOM --note "Plan d'exécution approuvé"
```

### 6. Démarrer l'orchestrateur

Dans l'agent Cursor, tape :

```text
/orchestrator
```

Ça exécute une passe de coordination : il regarde les Work Units que tu
viens d'approuver, démarre les subagents spécialisés (developer, QA,
reviewer...) pour celles qui sont prêtes, puis s'arrête. Pour le garder
actif pendant tout le reste de la session au lieu de retaper
`/orchestrator` après chaque étape, utilise le Custom Mode de Cursor :
ouvre le sélecteur de mode du chat, crée ou choisis un Custom Mode basé sur
le Skill `orchestrator`, et discute dans ce mode — il garde les
instructions de l'orchestrateur actives en continu.

Dans les deux cas, il ne démarre jamais toutes les Work Units et tous les
subagents en même temps. Il respecte les limites WIP (work-in-progress)
ci-dessous — par défaut, au maximum 3 Work Units actives et au maximum 2
subagents Developer écrivant du code simultanément — donc si tu as
approuvé 5 Work Units, seules 2 ou 3 démarrent immédiatement et les autres
démarrent automatiquement au fur et à mesure que les premières se
terminent ou libèrent une place.

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

Ce sont des réglages par défaut, pas des vérités universelles. Change-les dans la Constitution et versionne le changement.

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
