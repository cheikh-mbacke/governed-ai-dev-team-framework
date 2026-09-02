# Governed AI Dev Team Framework

**Dépôt source du framework** — fabrication, tests et distribution du produit.

Ce dépôt **n'a pas** de répertoire `.ai-team/` à la racine. L'identité fabrication
vit sous [`.fabric/`](.fabric/project-profile.yaml) ; le payload installable sous
[`distribution/payload/`](distribution/payload/). Voir [`AGENTS.md`](AGENTS.md).

Framework multi-agents gouverné par l'humain, livré aux **projets cibles après
installation** — voir [docs/operator/adopter-checklist.md](docs/operator/adopter-checklist.md).

**Version cible :** `0.7.0`

## Contribuer

[`AGENTS.md`](AGENTS.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`VERSIONING.md`](VERSIONING.md)

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

## Documentation produit (normative)

[`docs/product/`](docs/product/) — spécifications du framework livré aux projets installés.

## Prérequis

- Python **≥ 3.10**
- `PyYAML`, `jsonschema` (`requirements.txt`)
- Git recommandé pour les mises à jour transactionnelles
