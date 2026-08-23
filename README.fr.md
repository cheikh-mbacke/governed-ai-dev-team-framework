# Framework d'équipe IA de développement gouvernée

Ce dépôt est un framework prêt à mettre sur GitHub pour intégrer dans un projet une **équipe d'agents IA gouvernée par l'humain avec Cursor**.

L'idée n'est pas de fournir un gros prompt. Le dépôt matérialise l'organisation sous forme de fichiers versionnés : Constitution d'ingénierie, rôles, staffing, permissions, Work Units, Project State, preuves, review, audit indépendant et gates humaines.

## Installation dans un projet existant

```bash
python tools/install.py \
  --target /chemin/vers/projet-a \
  --project-id projet-a \
  --project-name "Projet A"
```

Ensuite dans le projet cible :

```bash
python scripts/ai-team/validate.py
python scripts/ai-team/status.py
```

## Première utilisation

1. Déposer la production humaine sous `docs/product/`.
2. Déclarer les sources autoritatives dans `.ai-team/sources/source-registry.yaml`.
3. Ouvrir le repo avec Cursor.
4. Lancer explicitement `/compile-project`.
5. Examiner le Project State, les Work Units, le graphe, les risques, la vérification et le staffing proposés.
6. Approuver G1.
7. Lancer `/orchestrator` ou utiliser ce Skill comme Custom Mode.
8. L'orchestrateur active ensuite les rôles utiles selon les Work Units, le risque, les dépendances, les permissions et les WIP limits.

Le simple fait d'ouvrir Cursor ne doit pas lancer l'équipe. Le framework distingue **chargement du système**, **compilation de la mission** et **activation du runtime**.

Voir `docs/OPERATOR_GUIDE.fr.md` pour le déroulement complet.
