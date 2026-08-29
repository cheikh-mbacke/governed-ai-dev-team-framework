# Modèle de sécurité — vue opérateur

Ce document résume les garanties et frontières **prouvées par la refonte `0.5.0`**. Il ne remplace pas la Constitution (`.ai-team/constitution/`).

## Autorité

| Acteur | Peut | Ne peut pas |
|---|---|---|
| **Opérateur humain** | Approuver gates G0–G4, consentir migrations, autoriser exports sensibles | Déléguer une décision produit à un agent sans gate |
| **Command Gateway** | Valider et persister les commandes noyau autorisées | Exécuter une commande sans enveloppe valide ou sans autorisation humaine quand requise |
| **Adaptateur** | Compiler le bundle, exécuter le runtime, produire des `RuntimeResult` | Écrire directement Work Units, Project State, décisions, preuves |
| **Agents / skills** | Agir dans les capacités du rôle et de l'outil | Contourner gates, auto-déclarer DONE, modifier l'allowlist sans revue humaine |

## Gates humaines (G0–G4)

- **G0** — baseline et sources autoritaires prêtes.
- **G1** — plan d'exécution approuvé.
- **G2** — décisions produit/architecture verrouillées pour la phase.
- **G3** — release candidate prête.
- **G4** — acceptation humaine finale.

Enregistrement via `scripts/ai-team/gov.py` (recommandé) ou wrapper legacy `record_gate.py` (déprécié — voir [deprecations.md](deprecations.md)).

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
- Confidentialité des exports feedback niveau `full` sans `--authorization-id` humain.
