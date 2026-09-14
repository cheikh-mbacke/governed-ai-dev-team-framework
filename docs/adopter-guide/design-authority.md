# Design Authority & Visual Conformance

Ce guide explique comment une maquette devient un **contrat produit autoritatif**,
traçable, versionné et vérifiable.

## Modes `design_mode`

| Mode | Intention |
|------|-----------|
| `conform` | Une référence autoritative existe ; l’agent la **reproduit**. |
| `adapt` | Référence autoritative, adaptations **uniquement** dans les free zones / tolérances. |
| `create` | Aucune référence autoritative ; création d’une direction. |
| `maintain` | Rester conforme au design system et à l’UI existante. |
| `explore` | Proposer plusieurs directions **sans** décision finale d’implémentation. |

La procédure créative `frontend-design` (alias de `create-frontend-design`) ne
doit être utilisée librement qu’en `create` ou `explore`. En `conform`,
utiliser `implement-approved-design`.

## Enregistrer une maquette

```bash
python scripts/ai-team/design.py register \
  --id DA-LOGIN-1 \
  --path designs/login.png \
  --authority authoritative \
  --by "Ada Designer" \
  --human "Ada Designer" \
  --screen login \
  --state content_available \
  --json
```

Niveaux d’autorité :

- `authoritative` — obligatoire ; **seul un humain autorisé** peut l’attribuer ;
- `advisory` — guidance, **jamais** un blocage automatique ;
- `inspiration_only` — inspiration ;
- `deprecated` — ne plus utiliser.

Le Core calcule `content_hash` (`sha256:…`). Les agents ne peuvent pas
s’autoproclamer auteurs d’une référence autoritative.

### Figma (optionnel)

```bash
python scripts/ai-team/design.py register \
  --id DA-FIGMA-1 \
  --uri "https://www.figma.com/file/…/Login" \
  --authority authoritative \
  --content-pin "sha256:…" \
  --by "Ada Designer" \
  --human "Ada Designer"
```

Figma n’est **pas** une dépendance obligatoire. Une URL distante autoritative
doit être **épinglée** (version/hash) avant d’être binding.

## Reference set et contrat

```bash
python scripts/ai-team/design.py create-reference-set \
  --id DRS-LOGIN \
  --title "Login screens" \
  --member "DA-LOGIN-1=route:/login=state:content_available=viewport:desktop" \
  --by "Ada Designer"

python scripts/ai-team/design.py compile-contract \
  --id DC-LOGIN \
  --mode conform \
  --reference-set DRS-LOGIN \
  --route /login \
  --screen login \
  --mandatory-text "Sign in" \
  --mandatory-element LoginForm \
  --by "Ada Designer"
```

Le Design Contract distingue origines : explicitement fourni, extrait,
inférence proposée, décision humaine, liberté agent. Une inférence n’est
jamais autoritative sans validation humaine.

## Lier à une Work Unit

```bash
python scripts/ai-team/design.py bind-work-unit \
  --work-unit WU-LOGIN-1 \
  --contract DC-LOGIN \
  --mode conform
```

Le Context Package multimodal inclut alors le contrat, les chemins/URI
vérifiés, hashes, tokens, free zones et le format de preuves attendu.
L’agent doit renvoyer le `context_package_hash`.

## Viewports et tolérances

Déclarés dans le Design Contract (`viewports`, `tolerances`) — jamais inventés
par le runner. Niveaux : `exact`, `tolerant_visual` (défaut), `structural`,
`behavioral`, `advisory`. Zones masquées, contenu dynamique et seuils font
partie du contrat.

## Vérification visuelle

```bash
python scripts/ai-team/design.py verify \
  --report-id VCR-1 \
  --contract DC-LOGIN \
  --work-unit WU-LOGIN-1 \
  --sha <commit40> \
  --verifier-role visual-qa \
  --implementer-role frontend-developer \
  --observations observations.json \
  --json
```

Chaque capture est liée à route, état, viewport, référence et commit.
Divergences : `defect`, `allowed_adaptation`, `environment_variance`,
`reference_ambiguity`, `design_system_conflict`, `product_decision_required`,
`reference_outdated`. Une divergence **blocking** contre une référence
autoritative empêche la progression. `advisory` ne bloque pas automatiquement.

## Changement de maquette

```bash
python scripts/ai-team/design.py reconcile \
  --id DR-1 \
  --previous DA-LOGIN-1 \
  --new DA-LOGIN-2 \
  --by "Ada Designer"
```

Seules les preuves et Work Units **réellement liées** sont invalidées.
L’historique du contrat précédent est préservé.

## Rôles

| Rôle | Responsabilité |
|------|----------------|
| `product-designer` | Structure les contrats et free zones ; ne valide pas sa propre implémentation |
| `design-system-steward` | Protège tokens/composants ; tranche les écarts au design system |
| `frontend-developer` | Implémente le contrat ; pas de changement de direction sans décision |
| `visual-qa` | Vérifie indépendamment ; ne modifie pas l’implémentation évaluée |

## Autres commandes

```bash
python scripts/ai-team/design.py status --json
python scripts/ai-team/design.py diff --artifact DA-LOGIN-1 --json
```

Les projets **sans frontend** n’ont aucune configuration supplémentaire à
fournir : le pipeline Design Authority reste inactif tant qu’aucune liaison
n’existe.
