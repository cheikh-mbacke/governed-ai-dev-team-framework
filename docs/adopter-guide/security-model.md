# Modèle de sécurité — vue opérateur

Ce document résume les garanties et frontières **prouvées par la refonte `0.5.0`**. Il ne remplace pas la Constitution (`.ai-team/constitution/`).

## Autorité

| Acteur | Peut | Ne peut pas |
|---|---|---|
| **Opérateur humain** | Approuver l’adoption, les gates G0–G4, consentir migrations, autoriser exports sensibles | Déléguer une décision produit à un agent sans gate ; adopter à moitié |
| **Command Gateway** | Valider et persister les commandes noyau autorisées | Exécuter une commande sans enveloppe valide ou sans autorisation humaine quand requise |
| **Adaptateur** | Compiler le bundle, exécuter le runtime, produire des `RuntimeResult` | Écrire directement Work Units, Project State, décisions, preuves |
| **Agents / skills** | Agir dans les capacités du rôle et de l'outil | Contourner gates, auto-déclarer DONE, modifier l'allowlist sans revue humaine |

Une fois l’adoption engagée, la gouvernance du framework est **exclusive** sur le dépôt : toute autorité concurrente (process, bots, agents hors Gateway) doit être éliminée, remappée ou dérogée explicitement. Voir [adoption-assessment.md](adoption-assessment.md).

## Gates humaines (G0–G4)

L’**assessment d’adoption** précède l’install et n’est pas une gate G0–G4.
Après installation, `/reconcile-project` impose une baseline empreintée avant la
première compilation et après toute dérive project-owned.

- **G0** — baseline de réconciliation et sources autoritaires prêtes ; en brownfield, inventaire as-built (écarts code↔intention, hors-scope, nettoyage) explicite pour le périmètre compilé.
- **G1** — plan d'exécution approuvé.
- **G2** — décisions produit/architecture verrouillées pour la phase.
- **G3** — release candidate prête.
- **G4** — acceptation humaine finale.

Enregistrement via `scripts/ai-team/gov.py` avec enveloppe `RecordGateDecision` (voir [deprecations.md](deprecations.md)).

## Capacités et moindre privilège

- Les rôles du bundle définissent des niveaux d'écriture (`none`, `branch`, etc.).
- La politique skills/permissions (Constitution §70) classe les skills `approved`, `restricted` ou `unknown`.
- Les skills d'orchestration tierces concurrentes au Control Plane restent **unknown** jusqu'à approbation G2.

## Persistance sûre

- Verrou fichier + journal de transaction + récupération (`recover`) sur les objets mutables.
- Idempotence via `idempotency_key` sur les Command Envelopes.
- Domain Events append-only **post-commit** — journal d'audit, pas source de vérité reconstructible en v1.

## Distribution et intégrité

- Snapshot manifesté (chemin, sha256, propriétaire) avant chaque update.
- Rollback Document 13 §11 restaure fichiers et manifestes ; **ne rétrograde pas** automatiquement des données créées sous un schéma incompatible.
- Refus par défaut si le dépôt cible est **Git sale** (`--allow-dirty` explicite requis).

## Ce qui n'est pas garanti

- Sécurité générale de l'IDE ou du modèle IA sous-jacent.
- `workspace_readonly` sur toutes les plateformes Windows — certains scénarios Document 14 L4 peuvent exiger un environnement qualifié.
- Remontée feedback : installer/utiliser le framework vaut acceptation (ADR-009). Export/submit full sans précaution de contenu. Seul `telemetry.collection: disabled` coupe la remontée.
