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

Pour le smoke test initial, sélectionne **Allowlist** dans `/config`. Active
les notifications si la plateforme les prend en charge ; sur certaines builds
Windows de Cursor CLI elles sont `unsupported` — ce n'est pas un échec du
smoke test. Après validation du routage des demandes de subagent, utilise
**Auto-review** au quotidien avec `/auto-review` : les permissions explicites
et le sandbox réduisent les interruptions, tandis que les opérations ambiguës
peuvent toujours demander une approbation. Ne choisis pas Run Everything pour
l'Orchestrateur gouverné.

Le fichier projet `.cursor/cli.json` ne peut contenir que `permissions.allow`
/ `permissions.deny`. L'absence de `approvalMode` ou `notifications` dans ce
fichier est attendue et ne doit pas être classée comme un échec.

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

Ce smoke test valide le **routage Allowlist CLI** d'un subagent vers le
terminal parent. Ce n'est pas un cycle produit avec Work Unit.

### Où l'exécuter

- Uniquement avec le Cursor CLI interactif : `agent --workspace "$PWD"`.
- **Ne pas** le lancer depuis le chat Agent de l'IU Cursor (outils Task /
  subagent IDE). Les permissions UI (`.cursor/permissions.json`) peuvent
  exécuter `whoami` sans invite Allowlist CLI ; un succès dans l'IDE ne
  valide **pas** ce parcours.

### Préflight d'environnement automatisé (d'abord)

Sépare les échecs d'environnement des échecs Allowlist. Avant de lancer
`agent`, utilise la commande Python 3 disponible sur l'hôte :

```bash
python scripts/ai-team/preflight.py
```

Ce préflight sans dépendance vérifie la configuration versionnée des hooks,
exécute `guard_shell.py` via le même lanceur portable que Cursor, contrôle les
permissions CLI projet et affiche le profil de capacité de la plateforme. Il
ne lit pas la configuration globale Cursor et ne simule pas une approbation
humaine : ces deux contrôles restent explicitement marqués `MANUAL`.

Ne modifie pas `.cursor/hooks.json` pour alterner entre `python` et `python3`.
Le lanceur versionné `.cursor/hooks/run_hook.cmd` sélectionne
`python3` / `python` sous POSIX et `python3` / `python` / `py -3` sous
Windows, tout en conservant le premier code de sortie du hook. Un interpréteur
absent ou un hook fail-closed cassé est signalé `BLOCKED` avant le scénario
d'autorisation.

### Choix de plateforme / subagent

| Objectif | Subagent | Notes |
| --- | --- | --- |
| Invite Allowlist / refus / autoriser une fois | `auth-smoke` | Sonde de routage multiplateforme avec `readonly: false` ; elle ne valide pas le vrai rôle Architecte |
| Parcours sandbox `workspace_readonly` | `architect` | Test d'intégration séparé avec `readonly: true` ; `SKIP` sous Windows natif, obligatoire sous WSL/Linux |

Ne pas affaiblir `architect` pour faire passer le smoke Allowlist.

### Procédure

1. Vérifie `agent --version`.
2. Depuis la racine du projet, lance `agent --workspace "$PWD"`.
3. Ouvre `/config`, mode **Allowlist**. Confirme que `Shell(whoami)` n'est
   **pas** dans l'allowlist globale ni projet. Les notifications peuvent être
   `unsupported` sur certaines builds Windows — à ignorer pour le verdict.
4. Confirme que `.cursor/cli.json` projet a `permissions.allow` /
   `permissions.deny`, **sans** `approvalMode` / `notifications`, et sans
   `Shell(whoami)`.
5. Mémorise la fin actuelle de `.ai-team/logs/cursor-events.jsonl` s'il
   existe.
6. Demande à l'agent CLI de lancer **`auth-smoke` en foreground** avec cette
   mission seule : exécuter exactement `whoami` ; rapporter stdout ou un
   refus d'autorisation ; ne pas éditer de fichiers ; ne pas substituer
   une autre commande.
7. Confirme une invite dans le terminal parent (`Not in allowlist: whoami`
   ou équivalent). **Skip / refuse** une fois (`n` ou Esc). N'ajoute pas
   `Shell(whoami)` à l'allowlist ; ne choisis pas Run Everything.
8. Colle le **même** prompt. Quand l'invite revient, choisis **Run once**
   (`y`). Confirme la sortie de `whoami` et un handoff normal du subagent.
9. Examine uniquement les nouvelles lignes de
   `.ai-team/logs/cursor-events.jsonl` pour `subagentStart`,
   `beforeShellExecution`, `afterShellExecution` (tentative autorisée) et
   `subagentStop`. Un `afterShellExecution` n'est pas exigé pour la
   tentative refusée.
10. Lance `git status --short`. Aucun changement inattendu hors le journal
    ignoré.
11. Lance `python scripts/ai-team/diagnose.py` (ou ta commande Python valide)
    et confirme l'absence de blocage silencieux.

### Ordre de diagnostic

1. `preflight.py` affiche-t-il `PASS` pour `hooks_config`, `guard_hook` et
   `project_cli` ?
2. L'invite Allowlist est-elle visible dans le terminal parent **CLI** ?
3. Seulement ensuite : Skip → même prompt → Run once → vérifier les hooks.

Une erreur de hook fail-closed ou un sandbox manquant est un échec
**d'environnement**, pas un verdict Allowlist.

N'augmente pas le WIP / les writers concurrents tant que ce smoke test n'a
pas réussi sur la version de Cursor CLI réellement utilisée.

Contrôle d'intégration obligatoire pour déclarer le support CLI complet :
sous WSL/Linux, répète une tentative shell avec `architect` pour confirmer
`workspace_readonly` sur cet hôte. Enregistre ce résultat séparément de celui
d'`auth-smoke`. Sous Windows natif, note
`SKIP — Cursor workspace_readonly indisponible`, jamais un échec ou un succès
Allowlist.

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
