# Baseline 0.4.x — référence comportementale

| Champ | Valeur |
|---|---|
| Framework version | `0.4.0` (`.ai-team/framework-version.json`) |
| Tag Git | `v0.4.0-baseline` |
| Work Unit | `WU-P0-BASELINE` |
| Captures | `tests/fixtures/legacy-0.4/cli/*.json` |
| Manifeste | `tests/fixtures/legacy-0.4/baseline-manifest.json` |

## CLI caractérisées

Les scénarios golden couvrent les parcours critiques installation, gate, done et feedback :

- **installation** : `install-fresh`, `install-missing-target`
- **gate** : `record-gate-g2`
- **done** : `check-done-missing`, `check-done-in-progress`
- **feedback** : `feedback-record`, `feedback-export-structured`
- **support** : `validate-clean`, `status-clean`, `diagnose-clean`, `preflight-json`

## Régénération

```bash
python tests/generate_golden_fixtures.py
```

Exécuter uniquement lors d'une révision de baseline explicitement approuvée (G2).
