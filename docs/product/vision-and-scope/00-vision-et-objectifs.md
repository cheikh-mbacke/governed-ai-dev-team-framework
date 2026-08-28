# Document 0 — Vision et objectifs

**Statut** : version 1.1 corrigée après audit indépendant du dépôt à la révision `9f77085eb2fc7a1f372556e9ad2714cf5318bd98`.

## 1. Problème observé

Le framework gouverne aujourd’hui le développement assisté par IA au moyen de gates humaines, de preuves, de revues indépendantes et d’objets d’état versionnés. Son implémentation est cependant couplée à Cursor : `.cursor/` est livré avec `.ai-team/`, plusieurs scripts connaissent les fichiers Cursor et certaines politiques de `.ai-team/constitution/` nomment directement Cursor.

Le couplage n’est donc pas limité à `.ai-team/`. La frontière physique du futur noyau devra classer explicitement :

- les schémas, politiques et données sous `.ai-team/` ;
- les scripts génériques et les scripts spécifiques à Cursor sous `scripts/ai-team/` ;
- `AGENTS.md` ;
- les fichiers d’installation et de migration ;
- `.cursor/`, qui appartient à l’Adaptateur Cursor.

## 2. Objectif de la refonte

La cible comporte :

- un **noyau de Gouvernance** agnostique de l’outil d’exécution ;
- un **Adaptateur Cursor** offrant au moins la parité fonctionnelle avec le dépôt actuel ;
- un **contrat publié et versionné** permettant de concevoir ultérieurement des Adaptateurs Claude Code et Codex CLI sans modifier le modèle de Gouvernance.

Claude Code et Codex CLI sont étudiés pour vérifier la portabilité du contrat ; leurs Adaptateurs ne sont pas implémentés dans cette refonte.

## 3. Domaine cœur

La valeur différenciante est la Gouvernance : autorité humaine explicite, travail décomposé, capacités bornées, preuves liées à un état vérifiable, revue et audit indépendants, et impossibilité pour un agent de s’auto-attribuer une décision produit ou de release.

Les artefacts d’un outil — frontmatter d’agent, fichiers de permissions, hooks et syntaxe de skill — ne font pas partie de ce domaine cœur.

## 4. Hors périmètre

- Session Cloud, son interface web/mobile et les sessions distantes ;
- l’implémentation des Adaptateurs Claude Code et Codex CLI ;
- le choix détaillé des packages, API et formats de migration, qui relève des spécifications techniques suivantes.

## 5. Critères de fin

La refonte est terminée lorsque :

1. chaque fichier livré est classé `core`, `adapter:<id>`, `distribution` ou `project-owned` ;
2. le noyau et ses interfaces publiques ne contiennent aucune dépendance à Cursor, Claude Code ou Codex ;
3. les écritures d’état faisant autorité passent par des commandes du noyau validées, et non par des écritures libres des Adaptateurs ;
4. l’Adaptateur Cursor conserve les comportements utiles actuels et passe une suite de conformité au contrat publié ;
5. les contrats de Rôle, Procédure et résultat sont versionnés et suffisent à étudier un autre Adaptateur ;
6. l’installation et la mise à jour préservent les fichiers possédés par le projet ainsi que le suivi des fichiers gérés.

## 6. Limites

- La parité du futur Adaptateur Cursor n’est pas encore démontrée.
- La faisabilité des Adaptateurs Claude Code et Codex CLI reste documentaire tant qu’aucun test de conformité n’est exécuté.
- La frontière exacte des scripts génériques et spécifiques doit être tranchée dans la conception technique.

## Sources observées

`pyproject.toml`, `tools/install.py`, `AGENTS.md`, `.ai-team/constitution/35-ui-ux-strategy.yaml`, `.ai-team/constitution/70-permissions-policy.yaml`, `scripts/ai-team/preflight.py`, `diagnose.py`, `propose_allowlist.py`, `validate.py`.
