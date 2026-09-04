# Contribuer

Respecter `VERSIONING.md`, `AGENTS.md` et, pour le payload livré, la Constitution
sous `distribution/payload/.ai-team/constitution/`.

## Dépôt source (`repository_kind: framework_source`)

Workflow complet : [`AGENTS.md`](AGENTS.md).

Layout fabrication : `.fabric/` (identité) + `distribution/payload/` (livré à
l'install). **Pas de `.ai-team/` à la racine.**

Parcours minimal :

1. Partir d'un `main` à jour ; branche `renov/<slug>` ou `fix/<slug>`.
2. Limiter le diff ; ajouter ou adapter tests et documentation.
3. Exécuter les vérifications listées dans `AGENTS.md`.
4. Ouvrir une pull request (modèle GitHub).

## Projets installés

Après `tools/install.py` sur un projet cible : voir
[docs/adopter-guide/adopter-checklist.md](docs/adopter-guide/adopter-checklist.md) et
[docs/adopter-guide/client-git-policy.md](docs/adopter-guide/client-git-policy.md).

## Changement de version

Mettre à jour `pyproject.toml`, `.fabric/framework-version.json`, `CHANGELOG.md`
et le candidat de release. Tag après validation du merge sur `main` — voir
`VERSIONING.md`.

## Signalement de sécurité

Ne publiez pas de secret ni de vulnérabilité exploitable dans une issue publique.
Utilisez le canal privé du mainteneur ou le signalement privé GitHub lorsqu'il est
activé.
