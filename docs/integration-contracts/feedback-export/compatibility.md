# Compatibilité du Feedback Export

## Règles producteur

- `format_version` sélectionne le contrat de données ;
- une version publiée est immuable ;
- un changement incompatible exige une nouvelle version de format ;
- le framework conserve les tests des niveaux de détail et du consentement ;
- le schéma présent dans le payload installé est la source de vérité exécutable.

## Règles consommateur

- embarquer une copie byte-identique du schéma accepté ;
- enregistrer dépôt source, chemin, version du framework et SHA-256 ;
- refuser ou isoler une version inconnue sans interprétation spéculative ;
- conserver des fixtures contractuelles pour chaque version acceptée ;
- faire évoluer indépendamment son protocole HTTP et sa version produit.

## Publication d’une évolution

1. modifier le producteur et son schéma dans le framework ;
2. exécuter les tests de contrat du framework ;
3. publier la nouvelle version du framework ;
4. importer explicitement le schéma dans le projet consommateur ;
5. vérifier son hash et exécuter la suite de compatibilité du consommateur ;
6. activer la version côté consommateur sans coupler les deux releases.
