# Carte documentaire du dépôt source

Ce dépôt fabrique et distribue le **Governed AI Dev Team Framework**. Sa
documentation source est séparée par système, autorité et public.

| Dossier | Système décrit | Public | Autorité | Distribué aux projets |
|---|---|---|---|---:|
| [`framework-design/`](framework-design/) | Produit framework | concepteurs et développeurs du framework | normative | non |
| [`framework-maintenance/`](framework-maintenance/) | Dépôt de fabrication | mainteneurs et release managers | opératoire source | non |
| [`adopter-guide/`](adopter-guide/) | Assessment pré-install et framework après installation | opérateurs des projets clients | guide d’utilisation | non |
| [`integration-contracts/`](integration-contracts/) | Frontières publiques du framework | producteurs et consommateurs | contrat d’intégration côté framework | non |

## Frontières non négociables

1. `docs/product/` est réservé au produit d’un **projet client installé**. Ce
   chemin ne doit pas exister dans le dépôt source du framework.
2. Les seuls fichiers livrés sont énumérés par le manifeste construit depuis
   `distribution/payload/`, `src/`, `adapters/`, les wrappers et `AGENTS.md`.
   Aucun dossier de cette documentation source n’est installé.
3. Un système externe possède son propre dépôt, ses exigences, son
   architecture, ses secrets, son exploitation et son cycle de release.
4. Ce dépôt peut publier un contrat consommé par un système externe, mais ne
   contient pas l’architecture interne ou le runbook de ce consommateur.
5. Dans un projet installé, `.ai-team/` contient le runtime et la gouvernance
   du framework ; `docs/product/` et les sources enregistrées sous
   `.ai-team/sources/` appartiennent au projet client.

## Carte des espaces physiques

```text
Dépôt source du framework
├── .fabric/                       identité de fabrication
├── docs/framework-design/         intention du framework
├── docs/framework-maintenance/    fabrication et release
├── docs/adopter-guide/            guides source, non installés
├── docs/integration-contracts/     frontières publiques seulement
├── distribution/payload/          payload réellement installable
├── src/                            noyau Python source
└── adapters/                       adaptateurs source

Projet client après installation
├── docs/product/                   produit client, project-owned
├── .ai-team/                       framework installé + état projet
├── .cursor/                        adaptateur compilé
└── scripts/ai-team/                wrappers installés

Projet externe
├── docs/product/                   exigences de ce projet externe
├── contracts/                      API qu’il expose
└── infrastructure/                 déploiement et secrets propres
```

La source de vérité des chemins installés est l’Installation Record produit par
l’installateur, jamais la présence d’un nom de dossier générique.
