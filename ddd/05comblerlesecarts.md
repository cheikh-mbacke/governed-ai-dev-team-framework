# Document 5 — Résolution des écarts du protocole

**Statut** : version 1.1 corrigée.

## 1. Résolution de l’Adaptateur actif

Le Project Profile cible porte seulement l’identité fonctionnelle de l’Adaptateur actif :

```json
"active_adapter_id": {
  "type": "string",
  "minLength": 1
}
```

La version installée ne doit pas être dupliquée dans le Project Profile. Elle est résolue dans l’Installation Record par correspondance avec `adapters[].id`. Invariant : `active_adapter_id` doit désigner exactement une entrée installée et compatible avec `core.version`.

Ce choix élimine la divergence possible entre `project-profile.adapter.version` et `framework-version.adapters[].version`.

## 2. Contrat du Control Plane

| Champ | Valeur cible |
|---|---|
| `role_id` | `control-plane` |
| Mandat | Coordonner compilation, staffing, contexte, vérification, revue, audit, release et gates sans acquérir d’autorité produit. |
| Écriture produit | `none` |
| Écriture de Gouvernance autoritaire | Commandes explicitement listées du noyau ; aucune écriture libre. Les décisions humaines restent hors de son autorité. |
| Écriture de signal | `record_observation` par port médié. |
| Capacité | Lecture du dépôt ; invocation des commandes nécessaires ; écriture directe refusée hors espaces techniques explicitement définis. |
| Approbation | Impossible de s’auto-approuver une gate, une acceptation humaine ou une release. |
| Procédures | `compile-project`, `orchestrator`, `build-context`, `impact-analysis`, `verify-work-unit`, `audit-release`, `prepare-acceptance`, `propose-profile`, rétrospective. |
| Modèle | Héritage par défaut. |
| Isolation | À déterminer par analyse de concurrence ; elle n’est pas présumée inutile. |

## 3. Capture du feedback

| Action | Portée actuelle | Autorité cible | Situation actuelle |
|---|---|---|---|
| `record` | Observation | Tout Rôle via une commande médiée | `feedback.py` écrit un fichier ; un agent Cursor `readonly` ne peut pas nécessairement l’invoquer directement. |
| `retrospective` | Work Unit ou projet | Control Plane | Le scope `increment` n’est ni schématisé ni implémenté. |
| `export` | Cross-projet | Humain ou commande munie d’un consentement vérifiable | Le script actuel n’exige aucune confirmation et persiste par défaut sous `.ai-team/metrics/`. |

Rendre `record` universel ne signifie pas donner un droit général d’écriture. L’Adaptateur transmet une requête minimale à un port du noyau qui valide `recorded_by`, le contenu et la destination.

Le consentement à l’export est désormais formulé comme **exigence cible**. Pour devenir un invariant, il doit être représenté par une gate, un jeton/flag explicite ou une commande humaine vérifiable.

## 4. Écarts supplémentaires à fermer

- définir le RuntimeResult et la validation des retours ;
- ajouter un writer et une convention de nom pour Decision Request ;
- implémenter l’invalidation des preuves par SHA ;
- définir l’atomicité et l’idempotence des commandes ;
- choisir si `increment` devient un scope réel ou disparaît définitivement du langage.

## 5. Limites

- `active_adapter_id` et l’Installation Record v2 n’ont pas encore été implémentés.
- Aucun deuxième Adaptateur ne valide ce modèle.
- La médiation d’Observation doit être testée avec les restrictions Cursor effectives.
- Les besoins d’isolation du Control Plane restent ouverts.

## Sources

`.ai-team/schemas/project-profile.schema.json`, `.cursor/skills/orchestrator/SKILL.md`, `compile-project/SKILL.md`, `capture-feedback/SKILL.md`, `scripts/ai-team/feedback.py`, `AGENTS.md`.
