"""ESI-laag — corp-hauling, locaties en routes (alles agressief gecached).

Bewust met platte `requests` i.p.v. de django-esi swagger-client: dat patroon
gebruikt characterscan ook en het is een stuk sneller/voorspelbaarder.
"""

import logging
import math
import time

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

ESI = "https://esi.evetech.net/latest"
UA = {"User-Agent": "aa-corp-hauling (Dutch Legions)"}

CONTRACTS_SCOPE = "esi-contracts.read_corporation_contracts.v1"
STRUCTURES_SCOPE = "esi-universe.read_structures.v1"

# Cache-tijden (seconden)
TTL_LOCATION = 7 * 24 * 3600
TTL_SYSTEM = 30 * 24 * 3600
TTL_ROUTE = 7 * 24 * 3600
TTL_CORP = 24 * 3600

# Structure-ids liggen ver boven de station-ids; alles daaronder is een NPC-station.
STRUCTURE_ID_FLOOR = 100_000_000


# Statussen waarbij opnieuw proberen zin heeft: ESI-foutlimiet, rate limit, storing.
RETRY_STATUS = {420, 429, 500, 502, 503, 504}
MAX_TRIES = 4

# Eén sessie voor het hele proces: zo hergebruiken we TLS-verbindingen in plaats
# van er honderden op te zetten. Dat scheelt niet alleen tijd — op Windows put
# een burst verse verbindingen de ephemeral poorten uit en dan gaan calls falen.
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=8, pool_maxsize=8, max_retries=0,
))


def _request(path, token=None, params=None):
    """Eén ESI-call met backoff. Geeft (gelukt, data).

    Het onderscheid tussen 'gelukt met een leeg antwoord' en 'mislukt' is hier
    essentieel: een mislukte call mag nooit als lege uitkomst gecached worden.
    """
    headers = dict(UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for poging in range(1, MAX_TRIES + 1):
        try:
            r = _session.get(
                f"{ESI}{path}",
                headers=headers,
                params={"datasource": "tranquility", **(params or {})},
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.info("ESI-call %s mislukt (poging %s): %s", path, poging, exc)
            time.sleep(min(2 ** poging * 0.25, 4))
            continue

        if r.status_code == 200:
            # Bijna door de foutlimiet heen? Even gas terugnemen.
            resterend = r.headers.get("X-Esi-Error-Limit-Remain")
            if resterend is not None and int(resterend) < 10:
                wachten = int(r.headers.get("X-Esi-Error-Limit-Reset", 5))
                logger.warning("ESI-foutlimiet bijna op (%s over) — %ss wachten",
                               resterend, wachten)
                time.sleep(min(wachten, 10))
            try:
                return True, r.json()
            except ValueError:
                return False, None

        if r.status_code in RETRY_STATUS and poging < MAX_TRIES:
            wachten = int(r.headers.get("Retry-After", 0)) or min(2 ** poging * 0.5, 8)
            logger.info("ESI %s gaf %s — %ss wachten en opnieuw (poging %s)",
                        path, r.status_code, wachten, poging)
            time.sleep(wachten)
            continue

        logger.info("ESI %s gaf %s: %s", path, r.status_code, r.text[:200])
        return False, None

    return False, None


def _get(path, token=None, params=None):
    """Eén ESI-call. Geeft None terug bij een fout (nooit een exception omhoog)."""
    _ok, data = _request(path, token=token, params=params)
    return data


def _paged(path, token=None):
    """Alle pagina's van een gepagineerde ESI-endpoint."""
    out, page = [], 1
    while page <= 20:  # harde bovengrens, contracten worden nooit zo veel
        rows = _get(path, token=token, params={"page": page})
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 1000:
            break
        page += 1
    return out


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

def _character_corp(character_id):
    """Huidige corp-id van een character (publiek, 1 dag gecached)."""
    key = f"cc_charcorp_{character_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _get(f"/characters/{character_id}/") or {}
    corp_id = data.get("corporation_id")
    if corp_id:
        cache.set(key, corp_id, TTL_CORP)
    return corp_id


def contracts_token(corp_id=None):
    """Een geldig token met de contracten-scope, bij voorkeur van de juiste corp.

    Werkt org-breed: we zoeken elk token met de scope en pakken het eerste dat
    bij een character in een player-corp hoort (net als de standings-lookup in
    characterscan). Geeft (token_string, corp_id) of (None, None).
    """
    from esi.models import Token

    for token in Token.objects.filter(scopes__name=CONTRACTS_SCOPE).order_by("-created"):
        char_corp = _character_corp(token.character_id)
        if not char_corp or char_corp < 98_000_000:  # NPC-corp → nutteloos
            continue
        if corp_id and char_corp != corp_id:
            continue
        try:
            return token.valid_access_token(), char_corp
        except Exception as exc:  # noqa: BLE001 — verlopen/ingetrokken token
            logger.info("Token van char %s onbruikbaar: %s", token.character_id, exc)
    return None, None


def structures_token():
    """Token met de structures-scope (optioneel — zonder blijven Upwell-namen leeg)."""
    from esi.models import Token

    for token in Token.objects.filter(scopes__name=STRUCTURES_SCOPE).order_by("-created"):
        try:
            return token.valid_access_token()
        except Exception:  # noqa: BLE001
            continue
    return None


def has_contracts_token():
    """Of er überhaupt een token met de contracten-scope gekoppeld is."""
    from esi.models import Token

    try:
        return Token.objects.filter(scopes__name=CONTRACTS_SCOPE).exists()
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Contracten
# --------------------------------------------------------------------------

def corp_contracts(corp_id=None, ttl=900, force=False):
    """Alle contracten van de corp uit ESI. Geeft (rows, corp_id)."""
    token, found_corp = contracts_token(corp_id)
    if not token:
        return [], corp_id
    corp_id = corp_id or found_corp

    key = f"cc_contracts_{corp_id}"
    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached, corp_id

    rows = _paged(f"/corporations/{corp_id}/contracts/", token=token)
    cache.set(key, rows, ttl)
    return rows, corp_id


def open_couriers(corp_id=None, ttl=900, force=False):
    """Alleen de openstaande koeriers-contracten. Geeft (rows, corp_id)."""
    rows, corp_id = corp_contracts(corp_id, ttl=ttl, force=force)
    couriers = [
        c for c in rows
        if c.get("type") == "courier" and c.get("status") == "outstanding"
    ]
    return couriers, corp_id


def resolve_names(ids):
    """{id: naam} voor characters/corps/etc. Onbekende ids ontbreken gewoon."""
    ids = [i for i in {int(i) for i in ids if i} if i]
    if not ids:
        return {}

    out, missing = {}, []
    for entity_id in ids:
        cached = cache.get(f"cc_name_{entity_id}")
        if cached is not None:
            out[entity_id] = cached
        else:
            missing.append(entity_id)

    for chunk in (missing[i:i + 1000] for i in range(0, len(missing), 1000)):
        try:
            r = _session.post(
                f"{ESI}/universe/names/",
                headers=UA,
                params={"datasource": "tranquility"},
                json=chunk,
                timeout=15,
            )
            rows = r.json() if r.status_code == 200 else []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Namen opzoeken mislukt: %s", exc)
            rows = []
        for row in rows:
            out[row["id"]] = row["name"]
            cache.set(f"cc_name_{row['id']}", row["name"], TTL_LOCATION)

    return out


# --------------------------------------------------------------------------
# Locaties en routes
# --------------------------------------------------------------------------

def location_info(location_id):
    """{name, system_id} voor een station of structure. Nooit None."""
    key = f"cc_loc_{location_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    info = {"name": "", "system_id": None}
    if location_id and location_id < STRUCTURE_ID_FLOOR:
        data = _get(f"/universe/stations/{location_id}/") or {}
        info = {"name": data.get("name", ""), "system_id": data.get("system_id")}
    else:
        token = structures_token()
        if token:
            data = _get(f"/universe/structures/{location_id}/", token=token) or {}
            info = {"name": data.get("name", ""), "system_id": data.get("solar_system_id")}

    if not info["name"]:
        info["name"] = f"Onbekende locatie #{location_id}"
    # Alleen echt gevonden locaties lang cachen; mislukte lookups kort.
    cache.set(key, info, TTL_LOCATION if info["system_id"] else 600)
    return info


def system_info(system_id):
    """{name, security} van een solar system. Nooit None."""
    if not system_id:
        return {"name": "?", "security": None}
    key = f"cc_sys_{system_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = _get(f"/universe/systems/{system_id}/") or {}
    info = {
        "name": data.get("name", f"#{system_id}"),
        "security": data.get("security_status"),
    }
    cache.set(key, info, TTL_SYSTEM if data else 600)
    return info


def system_position(system_id):
    """(x, y, z) van een solar system in meters, of None."""
    if not system_id:
        return None
    key = f"cc_pos_{system_id}"
    cached = cache.get(key)
    if cached is not None:
        return tuple(cached) if cached else None

    data = _get(f"/universe/systems/{system_id}/") or {}
    p = data.get("position") or {}
    pos = (p.get("x"), p.get("y"), p.get("z"))
    if None in pos:
        cache.set(key, [], 600)
        return None
    cache.set(key, list(pos), TTL_SYSTEM)
    return pos


LICHTJAAR_IN_METER = 9.4607e15


def lichtjaren(origin_system, destination_system):
    """Hemelsbrede afstand in lichtjaren tussen twee systemen, of None.

    Dat is wat telt voor een jump freighter: die springt op afstand, niet
    over gates.
    """
    if not origin_system or not destination_system:
        return None
    if origin_system == destination_system:
        return 0.0
    a = system_position(origin_system)
    b = system_position(destination_system)
    if not a or not b:
        return None
    return math.dist(a, b) / LICHTJAAR_IN_METER


def isotoop_prijs(type_id):
    """Jita-verkoopprijs van een brandstoftype (Fuzzwork-aggregaten, 1 uur gecached)."""
    key = f"cc_iso_{type_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        r = _session.get(
            "https://market.fuzzwork.co.uk/aggregates/",
            params={"station": 60003760, "types": str(type_id)},
            headers=UA, timeout=15,
        )
        data = r.json() if r.status_code == 200 else {}
        prijs = float(data.get(str(type_id), {}).get("sell", {}).get("percentile") or 0)
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Isotoopprijs ophalen mislukt: %s", exc)
        prijs = 0.0
    cache.set(key, prijs, 3600 if prijs else 600)
    return prijs


SKILLS_SCOPE = "esi-skills.read_skills.v1"
SKILL_JDC = 21611   # Jump Drive Calibration — +20% bereik per niveau
SKILL_JFC = 21610   # Jump Fuel Conservation — -10% verbruik per niveau

SKILL_JF = 29029    # Jump Freighters — trait 1311/1312 op de romp (+10% cargo, -10% brandstof p/n)

# Rassen-freighterskill per jump freighter (+5% cargo per niveau)
RASSEN_SKILL = {
    28844: 20526,   # Rhea   → Caldari Freighter
    28846: 20528,   # Nomad  → Minmatar Freighter
    28848: 20527,   # Anshar → Gallente Freighter
    28850: 20524,   # Ark    → Amarr Freighter
}

# Dogma-attributen van een schip met jump drive
ATTR_BEREIK = 867          # jumpDriveRange (LY)
ATTR_VERBRUIK = 868        # isotopen per lichtjaar
ATTR_BRANDSTOF = 866       # type-id van de isotoop
ATTR_CARGO_MULT = 149      # cargoCapacityMultiplier van een module (1,275 = +27,5%)


def schip_stats(type_id):
    """{naam, bereik_basis, isotopen_per_ly, brandstof_type_id, hold} van een schip."""
    key = f"cc_schip_{type_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = _get(f"/universe/types/{type_id}/") or {}
    attrs = {a["attribute_id"]: a["value"] for a in data.get("dogma_attributes", [])}
    stats = {
        "naam": data.get("name", f"#{type_id}"),
        "bereik_basis": float(attrs.get(ATTR_BEREIK) or 0),
        "isotopen_per_ly": float(attrs.get(ATTR_VERBRUIK) or 0),
        "brandstof_type_id": int(attrs.get(ATTR_BRANDSTOF) or 0),
        "hold": float(data.get("capacity") or 0),
    }
    cache.set(key, stats, TTL_SYSTEM if data else 600)
    return stats


def module_cargo_multiplier(type_id):
    """Cargo-vermenigvuldiger van een module (1,0 als die geen cargo-bonus geeft)."""
    key = f"cc_cargomult_{type_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = _get(f"/universe/types/{type_id}/") or {}
    attrs = {a["attribute_id"]: a["value"] for a in data.get("dogma_attributes", [])}
    mult = float(attrs.get(ATTR_CARGO_MULT) or 1.0)
    cache.set(key, mult, TTL_SYSTEM if data else 600)
    return mult


def resolve_type_ids(namen):
    """{naam_kleine_letters: type_id} voor itemnamen (via /universe/ids)."""
    namen = [n for n in {str(n).strip() for n in namen} if n]
    if not namen:
        return {}

    uit, missend = {}, []
    for naam in namen:
        cached = cache.get(f"cc_typeid_{naam.lower()}")
        if cached is not None:
            if cached:
                uit[naam.lower()] = cached
        else:
            missend.append(naam)

    for chunk in (missend[i:i + 100] for i in range(0, len(missend), 100)):
        try:
            r = _session.post(
                f"{ESI}/universe/ids/",
                headers=UA, params={"datasource": "tranquility"},
                json=list(chunk), timeout=15,
            )
            data = r.json() if r.status_code == 200 else {}
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Type-ids opzoeken mislukt: %s", exc)
            data = {}
        gevonden = {t["name"].lower(): t["id"] for t in (data.get("inventory_types") or [])}
        for naam in chunk:
            tid = gevonden.get(naam.lower())
            if tid:
                uit[naam.lower()] = tid
            # Onbekende namen ook cachen (als 0), anders vragen we ze elke keer opnieuw.
            cache.set(f"cc_typeid_{naam.lower()}", tid or 0, TTL_SYSTEM if tid else 3600)

    return uit


def character_skills(character_id):
    """{skill_id: niveau} van één character, of {} als er geen bruikbaar token is."""
    key = f"cc_skills_{character_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    from esi.models import Token

    niveaus = {}
    for token in Token.objects.filter(character_id=character_id,
                                      scopes__name=SKILLS_SCOPE).order_by("-created"):
        try:
            ok, data = _request(f"/characters/{character_id}/skills/",
                                token=token.valid_access_token())
        except Exception as exc:  # noqa: BLE001 — verlopen/ingetrokken token
            logger.info("Skills van %s niet op te halen: %s", character_id, exc)
            continue
        if ok and data:
            niveaus = {s["skill_id"]: s["trained_skill_level"]
                       for s in data.get("skills", [])}
            break

    cache.set(key, niveaus, 3600 if niveaus else 600)
    return niveaus


def route(origin_system, destination_system, flag="shortest"):
    """Lijst met system-ids van de route, of None als er geen route is."""
    if not origin_system or not destination_system:
        return None
    if origin_system == destination_system:
        return [origin_system]

    key = f"cc_route_{origin_system}_{destination_system}_{flag}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None  # lege lijst = "geen route", gecached

    systems = _get(
        f"/route/{origin_system}/{destination_system}/", params={"flag": flag}
    )
    cache.set(key, systems or [], TTL_ROUTE)
    return systems or None
