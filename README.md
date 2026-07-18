# AA Corp Hauling

Alliance Auth-plugin die de **open koeriers-contracten van je corporation** toont — met
per contract een berekening van wat een piloot er netto aan overhoudt.

## Wat je ziet

Per contract: de route (systeem → systeem, met de volledige stationsnamen), het aantal
sprongen, de beloning, de geschatte kosten, en de **netto winst**. Plus ISK per sprong,
ISK per m³, het volume, de collateral en wanneer het contract verloopt.

De lijst is sorteerbaar op netto winst, ISK per sprong, beloning, sprongen, volume en
verlooptijd — zodat meteen duidelijk is welk contract het meest oplevert.

### De winstberekening

Er zijn twee kostenmodellen, in te stellen in het admin-paneel.

**Over gates** — voor freighters en haulers:

```
netto winst = beloning − (sprongen × kosten per sprong)
```

Standaard wordt gerekend met de **kortste** route: de piloot kiest zelf hoe hij vliegt.
Zet je het op "veilig", dan telt de highsec-route. Het aantal sprongen van de andere
route staat er altijd bij.

**Jump freighter** — want die vliegt niet over gates maar springt op afstand:

```
netto winst = beloning − (lichtjaren × isotopen per LY × isotoopprijs)
```

De afstand is hemelsbreed tussen begin- en eindsysteem. Verbruik, brandstofsoort,
sprongbereik en vrachtruimte komen uit EVE zelf (dogma-attributen van het schip), de
isotoopprijs uit Jita.

### Persoonlijk profiel

Elk lid kan op `/corp-hauling/profiel/` zijn eigen schip kiezen (Ark, Anshar, Nomad,
Rhea). Skills worden standaard **uit EVE gelezen** — Jump Drive Calibration (+20%
bereik per niveau) en Jump Fuel Conservation (−10% verbruik per niveau) — of je vult ze
zelf in. De kosten op het bord zijn daarmee die van jóuw piloot, en contracten die niet
in je hold passen krijgen de melding *past niet*.

Zonder profiel valt alles terug op de corp-instellingen.

### Meekijken als beheerder

In het admin-paneel staan alle profielen bij elkaar: wie welk schip vliegt, welke skills
er gebruikt worden en waar die vandaan komen, plus het doorgerekende sprongbereik,
verbruik en vrachtruimte. De kolom *Signaal* laat zien waar iets niet klopt — bijvoorbeeld
`⚠ geen skill-token` als iemand "skills uit EVE" aan heeft staan maar er geen bruikbaar
token is, zodat er ongemerkt met de ingevulde waarden gerekend wordt.

### Route-waarschuwingen

| Badge | Betekenis |
|---|---|
| `omweg` | De kortste route gaat door low/nullsec; er bestaat een langere veilige route. Het aantal sprongen van beide routes wordt getoond. |
| `low/null` | Er is helemaal geen highsec-route — de bestemming ligt in low- of nullsec. |

## Installatie

```bash
pip install git+https://github.com/jweijdert-eng/aa-corp-hauling.git
```

Voeg `corphauling` toe aan `INSTALLED_APPS` in `local.py` en draai daarna:

```bash
python manage.py migrate
python manage.py collectstatic
```

### Periodiek verversen

```python
CELERYBEAT_SCHEDULE["corphauling_refresh"] = {
    "task": "corphauling.tasks.refresh_contracts",
    "schedule": 900,  # elke 15 minuten
}
```

Deze taak haalt de contracten op én warmt de locatie- en route-cache, zodat de pagina
voor gebruikers direct laadt.

## Instellen

1. Ken de permissie `corphauling.basic_access` toe aan de groep die de contracten mag zien.
2. Een director met de rol **Accountant** opent `/corp-hauling/` en klikt op
   **Token koppelen**. Dat is eenmalig — daarna verloopt alles automatisch.
3. Optioneel: admin-paneel → *Corp Hauling* → *Instellingen* voor de corp-id, de kosten
   per sprong en een minimale beloning.

### Benodigde ESI-scopes

| Scope | Waarvoor |
|---|---|
| `esi-contracts.read_corporation_contracts.v1` | de corp-hauling zelf (vereist) |
| `esi-universe.read_structures.v1` | namen van Upwell-structures (optioneel — zonder dit token tonen die als "onbekende locatie") |

## Permissies

| Permissie | Betekenis |
|---|---|
| `basic_access` | Kan de corp-hauling bekijken |
| `manage_settings` | Kan de instellingen beheren en het ESI-token koppelen |
