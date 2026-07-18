# AA Corp Hauling Tracker

Alliance Auth-plugin die per piloot toont **wat hij verdiende met koeriers-ritten**.

Op de pagina zie je, over al je gekoppelde characters samen:

- **Totaal verdiend** en het aantal voltooide ritten
- **Gemiddeld per dag** over je actieve dagen
- **Volume gehauld** met ISK per m³
- **Onderweg** (lopende ritten) en gefaalde ritten met verloren collateral
- Een **grafiek** van je verdiensten per dag
- Een **lijst** van alle ritten (klaar / onderweg / gefaald)

De data komt uit je persoonlijke contracten via ESI; de plugin houdt zelf niets
in de database bij. Stationnamen worden opgezocht, player-structures via een
optioneel structures-token.

## Installatie

```bash
pip install git+https://github.com/jweijdert-eng/aa-Corp-Hauling.git
```

Voeg `corphauling` toe aan `INSTALLED_APPS`, en draai `migrate` + `collectstatic`.

## Gebruik

Ken de permissie `corphauling.basic_access` toe aan wie z'n verdiensten mag zien.
Elk lid koppelt eenmalig zijn character (knop op de pagina) met de scope
`esi-contracts.read_character_contracts.v1`; daarna verschijnen de verdiensten
vanzelf.
