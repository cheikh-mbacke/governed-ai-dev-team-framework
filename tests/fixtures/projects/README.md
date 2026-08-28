# Witness projects — fixtures de référence

Projets témoins reproductibles pour les tests de migration et de distribution (Document 13 §3 Phase 0, Document 14 §2).

| Répertoire | Scénario | `project_id` |
|---|---|---|
| `clean/` | Installation fraîche, données projet minimales | `witness-clean` |
| `legacy/` | Données runtime, fichier géré obsolète, modifications utilisateur | `witness-legacy` |

## Contenu

### Projet témoin propre (`clean/`)

- Résultat d'une installation via `tools/install.py` dans une cible vide.
- `project-state.yaml` minimal (`phase: not_compiled`, aucune Work Unit).
- Aucun événement, evidence, observation ou autre artefact runtime.
- Profil projet personnalisé avec identifiants témoin uniquement.

### Projet témoin legacy (`legacy/`)

| Catégorie | Artefacts | Rôle |
|---|---|---|
| **Données runtime** | Work Units `WU-WITNESS-READY`, `WU-WITNESS-ACTIVE`, `WU-WITNESS-DONE` | États ready / in_progress / done |
| | Events, evidence, observations, retrospectives | Parcours d'exécution représentatif |
| | Gate G1, decision request, finding | Gates et décisions ouvertes |
| **Fichier géré obsolète** | `.cursor/skills/legacy-witness-removed/SKILL.md` | Simule une dérive de version (présent dans `managed_files` du manifeste installé mais absent du source courant) |
| **Modifications utilisateur** | `project-profile.yaml` (`extensions`, note personnalisée) | Métadonnées project-owned éditées |
| | `WU-WITNESS-ACTIVE` (rationale modifiée) | Work Unit éditée par l'opérateur |
| | `.ai-team/user/local-notes.yaml` | Fichier ajouté par l'utilisateur |

## Régénération

```bash
python tests/generate_witness_projects.py --write
```

Vérifier que les hashes commités correspondent toujours au générateur :

```bash
python tests/generate_witness_projects.py --verify
```

Le manifeste `witness-manifest.json` liste les SHA256 de chaque fichier des deux arbres.

## Tests

```bash
python -m pytest tests/test_witness_projects.py -q
```

## Notes

- Les deux témoins passent `python scripts/ai-team/validate.py` (des avertissements sur commandes non configurées ou sources absentes sont attendus).
- Ne régénérer qu'après changement intentionnel du framework installé ou du scénario témoin (décision G2 si impact baseline).
