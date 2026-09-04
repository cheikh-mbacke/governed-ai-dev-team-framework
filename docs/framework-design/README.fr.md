# Conception normative du framework

> **Périmètre :** spécifications du produit **Governed AI Dev Team Framework fabriqué dans ce dépôt**.
> Elles ne sont pas copiées dans les projets clients. Pour le workflow de fabrication, voir [`../../AGENTS.md`](../../AGENTS.md).

Ce dossier porte l’intention, les exigences, l’architecture et les critères de
conformité du framework lui-même. Dans un projet client installé, le chemin
`docs/product/` appartient exclusivement au produit de ce projet et
`.ai-team/sources/source-registry.yaml` enregistre ses sources autoritaires.

Les sept catégories ci-dessous structurent la spécification du framework :

- `vision-and-scope/` — le résultat visé, et ce qui est explicitement hors périmètre.
- `users-and-rules/` — qui utilise le système, leurs parcours, et les règles métier/invariants qui gouvernent le comportement.
- `requirements/` — exigences fonctionnelles et non fonctionnelles, et tout détail de spécification nécessaire pour éviter l'ambiguïté.
- `acceptance-criteria/` — les résultats observables qui font qu'un travail compte comme terminé.
- `architecture-and-constraints/` — architecture, contrats d'interface, et contraintes techniques/opérationnelles imposées (stack, versions, environnements).
- `security-and-compliance/` — contrôle d'accès, données, secrets, audit et exigences réglementaires.
- `references/` — données de référence, exemples, maquettes ou artefacts de preuve attendus.
