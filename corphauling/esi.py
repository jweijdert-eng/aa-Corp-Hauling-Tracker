"""ESI-laag — Corp Hauling verdiensten-tracker.

Leest per character z'n eigen contracten (character-contracts-scope) en zet
locatie-ids om naar namen. Platte `requests` i.p.v. de swagger-client: sneller
en voorspelbaarder. Alles agressief gecached.
"""

import logging
import threading
import time

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

ESI = "https://esi.evetech.net/latest"
UA = {"User-Agent": "aa-corp-hauling (Dutch Legions)"}

CHAR_CONTRACTS_SCOPE = "esi-contracts.read_character_contracts.v1"
STRUCTURES_SCOPE = "esi-universe.read_structures.v1"

# Cache-tijden (seconden)
TTL_LOCATION = 7 * 24 * 3600
STALE_KEEP_SECONDS = 7 * 86400   # verouderde SWR-data blijft zolang als terugval

# Structure-ids liggen ver boven de station-ids; alles daaronder is een NPC-station.
STRUCTURE_ID_FLOOR = 100_000_000

# Statussen waarbij opnieuw proberen zin heeft: ESI-foutlimiet, rate limit, storing.
RETRY_STATUS = {420, 429, 500, 502, 503, 504}
MAX_TRIES = 4

# Eén sessie voor het hele proces: hergebruik TLS-verbindingen i.p.v. er honderden
# op te zetten (scheelt tijd én voorkomt ephemeral-poort-uitputting op Windows).
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=8, pool_maxsize=8, max_retries=0,
))


def _swr(key, fresh_seconds, producer):
    """Geef meteen wat er is; ververs alleen op de achtergrond als het oud is.

    - Vers            → meteen terug.
    - Verouderd       → meteen terug + één achtergrond-refresh (met lock).
    - Niets in cache  → nu ophalen (blokkeert; alleen de allereerste keer).
    """
    box = cache.get(key)
    now = time.time()
    if isinstance(box, dict) and "__swr__" in box:
        if now < box["u"]:
            return box["v"]
        if cache.add(f"{key}:lock", 1, 120):
            def _refresh():
                try:
                    vers = producer()
                    cache.set(key, {"__swr__": True, "v": vers, "u": time.time() + fresh_seconds},
                              STALE_KEEP_SECONDS)
                except Exception:  # noqa: BLE001 — achtergrondwerk mag stil falen
                    logger.warning("Corp Hauling: achtergrond-refresh van %s mislukt",
                                   key, exc_info=True)
                finally:
                    cache.delete(f"{key}:lock")
            threading.Thread(target=_refresh, daemon=True).start()
        return box["v"]
    vers = producer()
    cache.set(key, {"__swr__": True, "v": vers, "u": now + fresh_seconds}, STALE_KEEP_SECONDS)
    return vers


def _request(path, token=None, params=None):
    """Eén ESI-call met backoff. Geeft (gelukt, data)."""
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
    while page <= 20:
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

def structures_token():
    """Token met de structures-scope (optioneel — zonder blijven Upwell-namen leeg)."""
    from esi.models import Token

    for token in Token.objects.filter(scopes__name=STRUCTURES_SCOPE).order_by("-created"):
        try:
            return token.valid_access_token()
        except Exception:  # noqa: BLE001
            continue
    return None


def _char_contracts_token(character_id):
    """Een geldig token van dít character met de character-contracten-scope."""
    from esi.models import Token

    for token in Token.objects.filter(character_id=character_id,
                                      scopes__name=CHAR_CONTRACTS_SCOPE).order_by("-created"):
        try:
            return token.valid_access_token()
        except Exception:  # noqa: BLE001 — verlopen/ingetrokken token
            continue
    return None


def character_contracts(character_id):
    """De persoonlijke contracten van één character (SWR-gecached).

    Geeft [] als er geen bruikbaar token met de scope is.
    """
    def _produce():
        token = _char_contracts_token(character_id)
        if not token:
            return []
        return _paged(f"/characters/{character_id}/contracts/", token=token)

    if not _char_contracts_token(character_id):
        return []
    return _swr(f"cc_charcontracts_{character_id}", 900, _produce)


def has_char_contracts_token(character_ids):
    """Of minstens één van deze characters een character-contracten-token heeft."""
    from esi.models import Token

    try:
        return Token.objects.filter(character_id__in=list(character_ids),
                                    scopes__name=CHAR_CONTRACTS_SCOPE).exists()
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Locaties
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
    cache.set(key, info, TTL_LOCATION if info["system_id"] else 600)
    return info
