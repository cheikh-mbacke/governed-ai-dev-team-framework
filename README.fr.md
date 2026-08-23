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

## Quickstart

### 1. Installer dans ton projet

```bash
python tools/install.py \
  --target /chemin/vers/projet-a \
  --project-id projet-a \
  --project-name "Projet A"
```

`install.py` n'écrase jamais un fichier déjà présent dans la cible (sauf
`--force`), et ne copie jamais `examples/`.

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

Voir `docs/SECURITY_MODEL.md`.

## Pour aller plus loin

- Checklist complète avant un vrai projet : `docs/ADOPTER_CHECKLIST.md`.
- Guide opérateur pas à pas (en français) : `docs/OPERATOR_GUIDE.fr.md`.
- Architecture, machine à états et pipeline de review : `docs/ARCHITECTURE.md`.
- Ce que couvrent (et ne couvrent pas) les contrôles Cursor : `docs/SECURITY_MODEL.md`.
- Correspondance entre ce dépôt et le document de cadrage de base : `docs/SOURCE_MAPPING.md`.

## Licence

MIT. Voir `LICENSE`.
