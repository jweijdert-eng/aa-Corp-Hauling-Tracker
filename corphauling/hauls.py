"""Persoonlijke haul-verdiensten: wat een piloot verdiende met koeriers-ritten.

Leest per character z'n eigen contracten en houdt de koeriers over die dít
account heeft aangenomen (acceptor = een van z'n characters). Dat is de
tegenhanger van het open-contractenbord: niet 'wat kan ik pakken' maar
'wat heb ik verdiend'.
"""

from datetime import datetime, timezone as dt_tz

from .esi import character_contracts, location_info
from .profit import fmt_isk

FINISHED = ("finished", "finished_contractor", "finished_issuer")


def _characters(user):
    """De EveCharacters van een gebruiker (main eerst)."""
    try:
        from allianceauth.eveonline.models import EveCharacter

        qs = list(EveCharacter.objects.filter(character_ownership__user=user))
        main = getattr(getattr(user, "profile", None), "main_character", None)
        if main:
            qs.sort(key=lambda c: c.character_id != main.character_id)
        return qs
    except Exception:  # noqa: BLE001
        return []


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _kort(naam):
    """'Jita IV - Moon 4 - CNAP' → 'Jita IV'; structure 'Systeem - Naam' → 'Systeem'."""
    return (naam or "").split(" - ")[0]


def user_hauls(user):
    """Alle koeriers-contracten die dit account heeft aangenomen, verrijkt.

    Geeft (hauls, corp_characters_met_token). Elke haul is een dict met de velden
    die de pagina nodig heeft (route, beloning, status, data, per m³).
    """
    chars = _characters(user)
    mijn_ids = {c.character_id for c in chars}
    naam_van = {c.character_id: c.character_name for c in chars}
    if not mijn_ids:
        return [], 0

    # Per character z'n contracten; koeriers die dit account aannam, ontdubbeld.
    ruw = {}
    met_token = 0
    for char in chars:
        cs = character_contracts(char.character_id)
        if cs:
            met_token += 1
        for c in cs:
            if c.get("type") != "courier":
                continue
            acc = c.get("acceptor_id")
            if not acc or acc not in mijn_ids:
                continue
            ruw[c["contract_id"]] = {**c, "_acc": acc}

    contracten = list(ruw.values())
    if not contracten:
        return [], met_token

    # Locatienamen: stations via cache/ESI, structures kan de server niet — dan id.
    loc_ids = {lid for c in contracten
               for lid in (c.get("start_location_id"), c.get("end_location_id")) if lid}
    loc_naam = {}
    for lid in loc_ids:
        info = location_info(lid)
        loc_naam[lid] = info["name"]

    hauls = []
    for c in contracten:
        beloning = float(c.get("reward") or 0)
        volume = float(c.get("volume") or 0)
        start = loc_naam.get(c.get("start_location_id"), "?")
        eind = loc_naam.get(c.get("end_location_id"), "?")
        voltooid = _parse(c.get("date_completed"))
        hauls.append({
            "id": c["contract_id"],
            "piloot": naam_van.get(c["_acc"], f"#{c['_acc']}"),
            "status": c.get("status"),
            "beloning": beloning,
            "beloning_fmt": fmt_isk(beloning),
            "collateral": float(c.get("collateral") or 0),
            "volume": volume,
            "volume_fmt": f"{volume:,.0f}".replace(",", "."),
            "per_m3": beloning / volume if volume else None,
            "per_m3_fmt": fmt_isk(beloning / volume) if volume else "—",
            "start": _kort(start), "eind": _kort(eind),
            "start_vol": start, "eind_vol": eind,
            "titel": c.get("title") or "",
            "date_completed": voltooid,
            "date_issued": _parse(c.get("date_issued")),
            "is_klaar": c.get("status") in FINISHED,
            "is_bezig": c.get("status") == "in_progress",
            "is_gefaald": c.get("status") == "failed",
        })

    hauls.sort(key=lambda h: h["date_completed"] or h["date_issued"] or datetime.min.replace(tzinfo=dt_tz.utc),
               reverse=True)
    return hauls, met_token


def haul_stats(hauls):
    """Samenvattende cijfers + verdiensten-per-dag voor de grafiek."""
    klaar = [h for h in hauls if h["is_klaar"] and h["date_completed"]]
    bezig = [h for h in hauls if h["is_bezig"]]
    gefaald = [h for h in hauls if h["is_gefaald"]]

    totaal = sum(h["beloning"] for h in klaar)
    volume = sum(h["volume"] for h in klaar)
    verlies = sum(h["collateral"] for h in gefaald)

    per_dag = {}
    for h in klaar:
        dag = h["date_completed"].date().isoformat()
        per_dag[dag] = per_dag.get(dag, 0) + h["beloning"]

    dagen = sorted(per_dag)
    max_dag = max(per_dag.values()) if per_dag else 0
    grafiek = [{
        "dag": d,
        "dag_kort": d[5:],                       # MM-DD
        "beloning": per_dag[d],
        "beloning_fmt": fmt_isk(per_dag[d]),
        "pct": round(per_dag[d] / max_dag * 100) if max_dag else 0,
    } for d in dagen]

    actieve_dagen = len(per_dag)
    return {
        "totaal_fmt": fmt_isk(totaal),
        "aantal_klaar": len(klaar),
        "gem_per_dag_fmt": fmt_isk(totaal / actieve_dagen) if actieve_dagen else "—",
        "actieve_dagen": actieve_dagen,
        "volume_fmt": f"{volume:,.0f}".replace(",", "."),
        "per_m3_fmt": fmt_isk(totaal / volume) if volume else "—",
        "aantal_bezig": len(bezig),
        "aantal_gefaald": len(gefaald),
        "verlies_fmt": fmt_isk(verlies),
        "grafiek": grafiek,
    }
