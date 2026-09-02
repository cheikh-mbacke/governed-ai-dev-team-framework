# Governed AI Dev Team Framework

Framework de développement multi-agents gouverné par l'humain : gates, Work Units, preuves, revue et audit indépendants.

**Version cible de cette refonte :** `0.7.0` (noyau agnostique + Adaptateur Cursor + Installation Record v3).

> **Ce dépôt est le dépôt source du framework** (`repository_kind: framework_source`).
> Il sert à développer et distribuer le framework — ce n'est **pas** un projet où le
> framework a été installé sur lui-même. Voir [`AGENTS.md`](AGENTS.md) avant toute
> contribution. Pour **adopter** le framework sur un autre projet, suivre la section
> « Adopter le framework » ci-dessous.

## Contribuer au framework (ce dépôt)

1. Lire [`AGENTS.md`](AGENTS.md) et [`CONTRIBUTING.md`](CONTRIBUTING.md).
2. Modifier `src/`, `adapters/`, le payload `.ai-team/` et les templates Cursor.
3. Valider avec `pytest` et `python scripts/ai-team/validate.py`.

## Adopter le framework (autre projet)

1. Lire [docs/operator/adopter-checklist.md](docs/operator/adopter-checklist.md).
2. Installer ou mettre à jour avec [docs/operator/operator-guide.md](docs/operator/operator-guide.md).
3. Migrer depuis `0.4.x` avec [docs/operator/upgrading.md](docs/operator/upgrading.md) si applicable.

## Documentation opérateur

| Guide | Contenu |
|---|---|
| [Architecture](docs/operator/architecture.md) | Noyau, Adaptateur, Distribution — vue d'ensemble |
| [Politique de versionnement](docs/operator/versioning-policy.md) | Axes de version, bumps, matrice de compatibilité |
| [Modèle de sécurité](docs/operator/security-model.md) | Autorité, gates, capacités, frontières |
| [Guide opérateur](docs/operator/operator-guide.md) | Install, update, validation, rollback, CLI |
| [Upgrading](docs/operator/upgrading.md) | Migration `0.4.x` → `0.7.0` |
| [Checklist adoptant](docs/operator/adopter-checklist.md) | Mise en service d'un projet |
| [Dépréciations](docs/operator/deprecations.md) | Échéances et remplacements |
| [Gouvernance GitHub](docs/operator/github-governance.md) | Protections de branches, tags et réglages de fusion |
| [Rupture historique 0.4.x](docs/operator/history-cutover-0.4.md) | Décision et conséquences de la nouvelle lignée Git |

## Contribution et versionnement

Voir [`CONTRIBUTING.md`](CONTRIBUTING.md), [`VERSIONING.md`](VERSIONING.md) et
[`CHANGELOG.md`](CHANGELOG.md).

## Documentation produit (normative)

Spécifications détaillées sous [`docs/product/`](docs/product/) — vision, architecture cible, tests de conformité (Document 14), etc.

## Prérequis

- Python **≥ 3.10**
- `PyYAML`, `jsonschema` (`requirements.txt`)
- Git recommandé pour les mises à jour transactionnelles

## Instructions agents

Voir [`AGENTS.md`](AGENTS.md) pour les règles de travail dans ce dépôt.
