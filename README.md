# Governed AI Dev Team Framework

**Dépôt source du framework** — fabrication, tests et distribution du produit.

Ce dépôt **n'a pas** de répertoire `.ai-team/` à la racine. L'identité fabrication
vit sous [`.fabric/`](.fabric/project-profile.yaml) ; le payload installable sous
[`distribution/payload/`](distribution/payload/). Voir [`AGENTS.md`](AGENTS.md).

Framework multi-agents gouverné par l'humain, livré aux **projets cibles après
installation** — assessment préalable puis checklist :
[adoption-assessment.md](docs/adopter-guide/adoption-assessment.md),
[project-reconciliation.md](docs/adopter-guide/project-reconciliation.md),
[adopter-checklist.md](docs/adopter-guide/adopter-checklist.md).

**Version cible :** `0.7.0`

## Contribuer

[`AGENTS.md`](AGENTS.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`VERSIONING.md`](VERSIONING.md)

## Documentation

| Espace | Contenu |
|---|---|
| [Carte documentaire](docs/README.md) | Frontières entre fabrication, framework installé, produit client et intégrations |
| [Conception du framework](docs/framework-design/) | Spécifications normatives du produit fabriqué ici |
| [Maintenance du framework](docs/framework-maintenance/) | Gouvernance GitHub, versions et historique du dépôt source |
| [Guide d’adoption](docs/adopter-guide/) | Assessment pré-install, installation, utilisation, sécurité et mise à jour |
| [Contrats d’intégration](docs/integration-contracts/) | Contrats publics produits par le framework, sans architecture des consommateurs |

Dans un projet client installé, `docs/product/` appartient exclusivement au
produit client. Ce chemin est volontairement absent du dépôt source du framework.

## Prérequis

- Python **≥ 3.10**
- `PyYAML`, `jsonschema` (`requirements.txt`)
- Git recommandé pour les mises à jour transactionnelles
