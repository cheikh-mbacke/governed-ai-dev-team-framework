# Guide d'utilisation avec Cursor CLI

*[Read in English](TERMINAL_GUIDE.md)*

Le framework prend en charge deux interfaces d'exécution équivalentes :

- l'interface graphique de Cursor ;
- le Cursor CLI interactif lancé avec `agent`.

Les deux modes partagent la même Constitution, les mêmes Work Units, états,
preuves, décisions, règles, Skills, subagents et hooks. Ils peuvent être
utilisés alternativement sur un même projet, mais jamais simultanément pour
écrire dans le même checkout Git.

## Ce qui est commun et ce qui est spécifique

| Élément | IU Cursor | Cursor CLI |
| --- | --- | --- |
| `.ai-team/` | commun | commun |
| `AGENTS.md` et `.cursor/rules/` | commun | commun |
| `.cursor/skills/` et `.cursor/agents/` | commun | commun |
| `.cursor/hooks.json` | commun | commun |
| Permissions d'exécution | `.cursor/permissions.json` | `.cursor/cli.json` |

Ne supprime aucun des deux fichiers de permissions. `.cursor/permissions.json`
conserve le comportement de l'IU ; `.cursor/cli.json` configure séparément le
CLI. Les blocages mécaniques de `.cursor/hooks/guard_shell.py` restent la
défense commune aux deux modes.

## 1. Préparer le CLI

Installe Cursor CLI selon la documentation officielle, puis vérifie :

```bash
agent --version
```

Lance toujours l'agent depuis le projet installé, pas depuis le dépôt du
framework :

```bash
cd /chemin/vers/ton/projet
agent --workspace "$PWD"
```

Le mode interactif est obligatoire pour un cycle gouverné qui peut demander
une autorisation ou une décision humaine. Le mode headless/print convient à
des contrôles non interactifs préautorisés, pas à l'orchestration complète.

## 2. Comprendre les permissions CLI

Cursor n'accepte que `permissions.allow` et `permissions.deny` dans le fichier
projet `.cursor/cli.json`. Le mode d'approbation et les notifications sont des
réglages globaux : configure-les avec `/config` ou dans
`~/.cursor/cli-config.json`, jamais dans le fichier projet.

Pour le smoke test initial, sélectionne **Allowlist** et active les
notifications dans `/config`. Après validation du routage des demandes de
subagent, utilise **Auto-review** au quotidien avec `/auto-review` : les
permissions explicites et le sandbox réduisent les interruptions, tandis que
les opérations ambiguës peuvent toujours demander une approbation. Ne choisis
pas Run Everything pour l'Orchestrateur gouverné.

Le fichier projet livré préautorise seulement :

- la lecture du dépôt, hors secrets courants ;
- l'écriture du projet, hors Constitution et fichiers de contrôle des
  permissions/hooks ;
- les commandes Git de consultation ;
- les scripts de validation, statut, diagnostic et Definition of Done.

Les commandes de build, lint et test dépendent de la stack du projet. Après le
smoke test, ajoute leurs formes exactes à `.cursor/cli.json` après avoir
renseigné `.ai-team/project-profile.yaml`. En mode Allowlist, toute commande
non listée demande une approbation. En mode Auto-review, elle passe par le
sandbox puis, si nécessaire, par le classifieur ou l'approbation humaine. Une
règle `deny` est un refus ferme, pas une demande d'approbation ; réserve-la aux
secrets, à la Constitution et aux opérations explicitement dangereuses.

## 3. Premier cycle terminal : profil conservateur

Avant le premier cycle CLI, réduis temporairement et versionne les limites
suivantes dans la Constitution du projet :

```yaml
# .ai-team/constitution/10-project-strategy.yaml
wip_limits:
  max_active_work_units: 1
  max_concurrent_code_writers: 1
```

```yaml
# .ai-team/constitution/60-staffing-policy.yaml
defaults:
  maximum_active_role_instances: 3
  maximum_code_writers: 1
```

Effectue ce changement avant de compiler le cycle. La Constitution ne doit
jamais être modifiée au milieu d'un cycle actif. Quand le smoke test ci-dessous
est concluant, tu peux augmenter progressivement ces valeurs.

## 4. Exécuter le workflow

Dans Cursor CLI :

```text
/compile-project

Compile le projet à partir de @docs/product/. N'implémente aucun code
produit — arrête-toi après avoir produit le plan d'exécution pour mon
approbation.
```

Dans un second terminal :

```bash
python scripts/ai-team/status.py
python scripts/ai-team/record_gate.py G1 approved --by TON_NOM --note "Plan d'exécution approuvé"
```

Puis dans Cursor CLI :

```text
/orchestrator
```

Tu peux invoquer le Skill comme Custom Mode persistant depuis le menu `/` avec
`Alt+Enter` ou `Option+Enter`. Garde un second terminal ouvert pour
`status.py` et `diagnose.py` : une décision de gate doit être enregistrée par
l'humain, pas absorbée dans un simple message de chat.

## 5. Smoke test obligatoire des autorisations de subagent

Exécute ce test sur une branche de test et avec une Work Unit jetable :

1. vérifie que `agent --version` fonctionne ;
2. lance `agent --workspace "$PWD"` ;
3. ouvre `/config`, sélectionne Allowlist et active les notifications ;
4. vérifie que `.cursor/cli.json` existe et que `Shell(whoami)` n'est pas
   préautorisé ;
5. invoque `/orchestrator` avec une Work Unit READY sans modification produit ;
6. demande au subagent d'exécuter exactement la commande inoffensive `whoami` ;
7. vérifie que la demande apparaît dans le terminal parent et que la
   notification est visible ;
8. refuse une première fois et vérifie qu'un `BLOCKER` ou une
   `CLARIFICATION_REQUEST` est écrit avant l'arrêt ;
9. recommence, autorise la commande et vérifie que le subagent reprend puis
   produit son handoff ;
10. vérifie que `.ai-team/logs/cursor-events.jsonl` contient
   `subagentStart`, `beforeShellExecution`, `afterShellExecution` et
   `subagentStop` ;
11. lance `python scripts/ai-team/diagnose.py` et confirme l'absence de blocage
   silencieux.

Ne passe pas à plusieurs Work Units ou writers concurrents tant que ces onze
points ne sont pas tous observés sur la version de Cursor CLI réellement
utilisée.

## 6. Alterner entre IU et CLI

Avant de changer de mode :

1. laisse l'agent courant terminer ou arrête-le explicitement ;
2. vérifie qu'aucune autorisation n'est encore en attente ;
3. lance `python scripts/ai-team/status.py` puis
   `python scripts/ai-team/diagnose.py` ;
4. vérifie `git status` et enregistre le handoff ou le BLOCKER nécessaire ;
5. seulement ensuite, ouvre l'autre interface sur le même checkout.

Pour deux writers réellement concurrents, utilise des worktrees distincts.
Cursor CLI accepte `agent --worktree WU-XXX`, mais l'Orchestrateur doit rester
la seule autorité qui alloue les Work Units et rassemble leurs résultats.

## 7. Limite de sécurité

Le terminal n'ajoute pas une frontière de sécurité entre l'agent et ton compte
système. Conserve hors du modèle les protections de branche, contrôles CI,
CODEOWNERS, secrets et credentials de production. Voir `SECURITY_MODEL.md`.
