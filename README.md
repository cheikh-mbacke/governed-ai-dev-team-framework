# Governed AI Dev Team Framework

Framework de développement multi-agents gouverné par l'humain : gates, Work Units, preuves, revue et audit indépendants.

**Version cible de cette refonte :** `0.7.0` (noyau agnostique + Adaptateur Cursor + Installation Record v3).

## Démarrage rapide

1. Lire [docs/operator/adopter-checklist.md](docs/operator/adopter-checklist.md).
2. Installer ou mettre à jour avec [docs/operator/operator-guide.md](docs/operator/operator-guide.md).
3. Migrer depuis `0.4.x` avec [docs/operator/upgrading.md](docs/operator/upgrading.md) si applicable.

## Documentation opérateur

| Guide | Contenu |
|---|---|
| [Architecture](docs/operator/architecture.md) | Noyau, Adaptateur, Distribution — vue d'ensemble |
| [Modèle de sécurité](docs/operator/security-model.md) | Autorité, gates, capacités, frontières |
| [Guide opérateur](docs/operator/operator-guide.md) | Install, update, validation, rollback, CLI |
| [Upgrading](docs/operator/upgrading.md) | Migration `0.4.x` → `0.5.0` |
| [Checklist adoptant](docs/operator/adopter-checklist.md) | Mise en service d'un projet |
| [Dépréciations](docs/operator/deprecations.md) | Échéances et remplacements |

## Documentation produit (normative)

Spécifications détaillées sous [`docs/product/`](docs/product/) — vision, architecture cible, tests de conformité (Document 14), etc.

## Prérequis

- Python **≥ 3.10**
- `PyYAML`, `jsonschema` (`requirements.txt`)
- Git recommandé pour les mises à jour transactionnelles

## Instructions agents

Voir [`AGENTS.md`](AGENTS.md) pour les règles de travail dans ce dépôt.
