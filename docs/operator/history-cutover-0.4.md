# Rupture historique entre 0.4.x et le nouveau `main`

## Décision

La rupture d'ascendance est volontaire. Un blocage technique rencontré pendant la refonte
a conduit l'autorité humaine à repartir sur une nouvelle lignée Git. L'opération n'avait
pas été documentée au moment de son exécution ; cette page constitue son enregistrement
rétrospectif, approuvé le 31 août 2026 dans `DEC-GIT-GOVERNANCE-20260831`.

La nature détaillée du blocage n'est pas reconstruite ici faute d'élément vérifiable plus
précis. Elle pourra être ajoutée ultérieurement sans modifier les faits Git ci-dessous.

## Références conservées

- ancienne lignée : `origin/release/0.4.0`, dernier SHA `981bf43c1c0cbabfd729e8e410ed288c12ce8ca9` ;
- archive stable : tag annoté `v0.4.0` sur ce même commit ;
- nouvelle lignée : commit racine `309ee6715da84562f92622f844802e979463b222` ;
- branche canonique actuelle : `main`.

Ces lignées n'ont aucun ancêtre commun. Elles ne doivent pas être raccordées par une
réécriture, un graft publié ou le déplacement d'un tag.

## Conséquences

- les comparaisons entre 0.4.x et les versions suivantes utilisent deux arbres ou archives,
  pas une simple plage `v0.4.0..main` ;
- `git bisect` ne traverse pas la coupure ;
- les preuves et SHA de l'ancienne lignée restent valides seulement dans cette lignée ;
- les changelogs doivent mentionner explicitement la coupure ;
- la branche et le tag d'archive doivent être protégés contre la suppression et le
  force-push.

Toute future rupture d'historique requiert avant exécution : décision humaine enregistrée,
motif technique, refs avant/après, inventaire des preuves invalidées, sauvegarde vérifiée,
plan de communication et procédure de restauration.
