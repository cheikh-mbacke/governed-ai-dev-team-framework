# Changelog

Les changements notables sont consignés ici. Le format suit Keep a Changelog et les
versions produit suivent Semantic Versioning.

## [Unreleased]

### Added

- Décision **DEC-003** — modèle `framework_source`, increment **INC-0.7.0**, clôture mode nuit, politique G3/G4 et nettoyage doc.
- `scripts/ai-team/sync_source_manifest.py` et validation `framework_source` dans `validate.py`.

### Changed

- Documentation produit alignée sur `gov.py` et Installation Record v3 (suppression des références actives à `record_gate.py`).
- **WU-MODE-NUIT-CONFORMITY** clôturée (L4 réel documenté hors scope 0.7.0).

### Fixed

- Séparation explicite dépôt framework vs projet installé ; suppression du record dogfood incohérent.

## [0.7.0] - Non publiée

- Version actuellement déclarée dans les sources. Aucun tag ni GitHub Release ne doit être
  créé avant clôture de `WU-GIT-GOVERNANCE` et validation du SHA de fusion.

## [0.6.0] - 2026-08-30

- Release de clôture de la migration enregistrée dans l'état projet.
- Anomalie connue : le tag léger historique `v0.6.0` pointe vers un commit dont
  `pyproject.toml` déclare encore `0.4.0`. Le tag est conservé intact ; il ne constitue pas
  un précédent pour les releases futures.

## [0.5.0] - Non publiée

- Incrément planifié et accepté dans le cycle de migration, sans tag Git stable publié.

## [0.4.0] - 2026-08-30

- Dernière lignée monolithique conservée sous `release/0.4.0` et par le tag annoté
  `v0.4.0`.
