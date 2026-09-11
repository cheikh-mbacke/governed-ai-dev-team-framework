# Modifier la configuration en cours de développement

Le `Project Profile` peut évoluer après l'installation sans édition directe du
YAML. Les changements passent par le Command Gateway : ils sont validés,
transactionnels, autorisés par un humain et historisés dans
`.ai-team/profile-changes/`.

Afficher le profil et sa révision :

```bash
python scripts/ai-team/configure.py show
```

Changer le profil d'autonomie pour les prochains Runs :

```bash
python scripts/ai-team/configure.py autonomy unattended_conservative \
  --reason "Le périmètre est stabilisé et le plan G1 est approuvé" \
  --authorized-by "Nom de l'autorité humaine"
```

Appliquer plusieurs réglages à partir d'un patch YAML :

```yaml
# profile-patch.yaml
communication:
  language: français
commands:
  unit_test: python -m pytest tests/ -q
notifications:
  email:
    enabled: false
```

```bash
python scripts/ai-team/configure.py apply --patch profile-patch.yaml \
  --reason "Alignement de l'outillage du projet" \
  --authorized-by "Nom de l'autorité humaine"
```

Les sections mutables sont `autonomy`, `commands`, `communication`,
`human_authorities`, `notifications`, `paths`, `release` et
`runtime_environments`. L'identité du projet, l'état d'installation,
l'adaptateur actif et la télémétrie ne sont pas modifiables par cette commande.

Un changement de profil s'applique uniquement aux **Runs ouverts ensuite**.
Chaque Run conserve le preset et la politique effective figés à son ouverture.
Pour réduire immédiatement le pouvoir d'un Run actif, utiliser les mécanismes
de révocation, d'arrêt ou `TightenExecutionCeiling`; l'autonomie d'un Run actif
ne peut jamais être élargie par un changement de profil.
