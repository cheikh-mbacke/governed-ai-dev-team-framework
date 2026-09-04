# Réconcilier un projet avant compilation

Après installation, lancez `/reconcile-project` avant `/compile-project`. Cette
étape transforme la matière humaine et l’état observé du dépôt en une baseline
cohérente, explicite et vérifiable.

## Ce que fait la commande

1. Vérifie la matière humaine minimale et ses sources autoritaires.
2. Inventorie code, architecture, tests, données, dépendances, documentation,
   infrastructure et dette.
3. Compare l’existant à l’intention humaine.
4. Classe chaque surface et construit une matrice de convergence.
5. Demande les décisions et approbations humaines manquantes.
6. Applique uniquement les actions approuvées.
7. Vérifie le résultat et empreinte la baseline.

Le rapport est conservé sous
`.ai-team/reconciliation/baseline.yaml`. La commande peut être interrompue puis
reprise ; ne supprimez pas le rapport pour contourner une décision ouverte.

## Contrôle manuel

```bash
python scripts/ai-team/reconcile_project.py check
```

Une sortie réussie autorise `/compile-project`. Une modification ultérieure d’un
fichier project-owned rend l’empreinte obsolète : relancez `/reconcile-project`,
réévaluez les écarts concernés, puis finalisez à nouveau.

## Sécurité

L’analyse n’autorise pas automatiquement les actions `migrate`, `rewrite`,
`isolate` ou `delete`. Elles nécessitent une référence d’approbation humaine dans
le rapport. Les décisions ambiguës restent bloquantes et le dépôt existant ne sert
jamais de substitut à l’intention produit.

## Différence avec les autres commandes

| Commande | Moment | Rôle |
|---|---|---|
| `tools/assess.py` | Avant installation | Mesurer le coût et les conflits d’adoption, sans mutation |
| `/reconcile-project` | Après installation, avant compilation | Faire converger intention et existant, puis établir la baseline |
| `/compile-project` | Après réconciliation | Produire le plan, les Work Units et le dossier G1 |
| `preflight.py` | Avant un Run | Vérifier les prérequis d’exécution |
| `diagnose.py` | En exploitation | Diagnostiquer l’état gouverné installé |
