"""Rekenlaag — van een ruw ESI-contract naar een regel met netto winst.

Los gehouden van de views zodat de berekening zelfstandig te testen is.
"""

from datetime import datetime, timezone as dt_timezone

import math

from .esi import isotoop_prijs, lichtjaren, location_info, route, system_info


def fmt_isk(value):
    """1234567890 → '1,23 mld'. Kort genoeg voor een tabelcel."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    for grens, achtervoegsel in ((1e12, "bln"), (1e9, "mld"), (1e6, "mln"), (1e3, "k")):
        if abs(value) >= grens:
            return f"{value / grens:,.2f} {achtervoegsel}".replace(",", ".")
    return f"{value:,.0f}".replace(",", ".")


def _parse_date(value):
    """ESI-datum ('2026-07-18T12:00:00Z') → aware datetime, of None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sec_klasse(security):
    """CSS-klasse voor de securitystatus — zelfde indeling als in EVE zelf."""
    if security is None:
        return "cc-sec-onbekend"
    afgerond = round(security, 1)
    if afgerond >= 0.5:
        return "cc-sec-hi"
    if afgerond > 0.0:
        return "cc-sec-low"
    return "cc-sec-null"


def _endpoint(location_id):
    """Locatie + het systeem eromheen, klaar voor weergave."""
    loc = location_info(location_id)
    sys_info = system_info(loc["system_id"])
    security = sys_info["security"]
    return {
        "name": loc["name"],
        "system_id": loc["system_id"],
        "system": sys_info["name"],
        "security": security,
        # Voor de weergave: afgerond getal + kleurklasse
        "sec_fmt": f"{round(security, 1):.1f}" if security is not None else "",
        "sec_klasse": _sec_klasse(security),
    }


def _routes(origin_system, destination_system):
    """Sprongen via de kortste én de veilige (highsec) route.

    We leiden het gevaar af uit het verschil tussen beide routes — dat scheelt
    een security-lookup per systeem op de route:
      - geen veilige route  → bestemming ligt in low/null
      - veilige route langer → de kortste route snijdt door low/null
    """
    shortest = route(origin_system, destination_system, flag="shortest")
    secure = route(origin_system, destination_system, flag="secure")

    jumps_short = len(shortest) - 1 if shortest else None
    jumps_secure = len(secure) - 1 if secure else None

    if jumps_secure is None:
        gevaar = "none"      # helemaal geen highsec-route
    elif jumps_short is not None and jumps_secure > jumps_short:
        gevaar = "shortcut"  # kortste route gaat door low/null, veilige route bestaat
    else:
        gevaar = "safe"

    return {
        "jumps_shortest": jumps_short,
        "jumps_secure": jumps_secure,
        "danger": gevaar,
    }


def jf_kosten(afstand_ly, par):
    """Brandstofkosten van een jump-freighter-run over `afstand_ly` lichtjaar.

    `par` komt uit piloot.parameters(): daarin zitten het schip en de skills van
    déze gebruiker al verrekend (isotopen per LY is dus al na Jump Fuel
    Conservation, en het bereik al na Jump Drive Calibration).
    """
    if afstand_ly is None:
        return None, None, None
    isotopen = afstand_ly * par["isotopen_per_ly"]
    bereik = par["bereik_ly"] or 0
    sprongen = math.ceil(afstand_ly / bereik) if bereik else None
    return isotopen * par["isotoop_prijs"], isotopen, sprongen


def enrich(contract, isk_per_jump, route_voorkeur="kort", cfg=None, par=None):
    """Eén ESI-contract → dict met alles wat de tabel nodig heeft.

    `route_voorkeur` bepaalt met welke route we rekenen: 'kort' (standaard —
    de piloot kiest zelf zijn route en neemt meestal de kortste) of 'veilig'
    (highsec waar mogelijk). Het aantal sprongen van de andere route wordt
    altijd meegegeven, zodat de tabel beide kan tonen.
    """
    reward = float(contract.get("reward") or 0)
    collateral = float(contract.get("collateral") or 0)
    volume = float(contract.get("volume") or 0)

    start = _endpoint(contract.get("start_location_id"))
    end = _endpoint(contract.get("end_location_id"))
    r = _routes(start["system_id"], end["system_id"])

    # De sprongen waar we mee rekenen, met de andere route als terugval.
    if route_voorkeur == "veilig":
        jumps = r["jumps_secure"] if r["jumps_secure"] is not None else r["jumps_shortest"]
        jumps_anders = r["jumps_shortest"]
    else:
        jumps = r["jumps_shortest"] if r["jumps_shortest"] is not None else r["jumps_secure"]
        jumps_anders = r["jumps_secure"]

    jf = cfg is not None and getattr(cfg, "kosten_model", "gates") == "jf" and par is not None
    afstand_ly = lichtjaren(start["system_id"], end["system_id"]) if jf else None
    isotopen = None

    if jf:
        # Een jump freighter springt op afstand; gates en hun sprongen doen
        # er dan niet toe, alleen de lichtjaren en de brandstof.
        cost, isotopen, jf_sprongen = jf_kosten(afstand_ly, par)
        if jf_sprongen is not None:
            jumps = jf_sprongen
        net = reward - cost if cost is not None else None
        per_jump = (net / jumps) if (net is not None and jumps) else net
    elif jumps is None:
        cost = None
        net = None
        per_jump = None
    else:
        cost = jumps * isk_per_jump
        net = reward - cost
        per_jump = net / jumps if jumps else net

    return {
        "id": contract.get("contract_id"),
        "title": contract.get("title") or "",
        "issuer_id": contract.get("issuer_id"),
        "reward": reward,
        "reward_fmt": fmt_isk(reward),
        "collateral": collateral,
        "collateral_fmt": fmt_isk(collateral),
        "volume": volume,
        "volume_fmt": f"{volume:,.0f}".replace(",", "."),
        "start": start,
        "end": end,
        "jumps": jumps,
        "jumps_shortest": r["jumps_shortest"],
        "jumps_secure": r["jumps_secure"],
        "danger": r["danger"],
        "route_voorkeur": route_voorkeur,
        # Jump-freighter-gegevens (leeg bij het gate-model)
        "jf": jf,
        "afstand_ly": afstand_ly,
        "afstand_ly_fmt": f"{afstand_ly:.1f}".replace(".", ",") if afstand_ly is not None else "?",
        "isotopen": isotopen,
        "isotopen_fmt": f"{isotopen:,.0f}".replace(",", ".") if isotopen is not None else "?",
        # Past de vracht in het schip van deze piloot?
        "te_groot": bool(jf and par and par.get("hold") and volume > par["hold"]),
        # Sprongen via de níet-gekozen route; alleen tonen als het verschilt.
        "jumps_anders": jumps_anders if jumps_anders != jumps else None,
        # Losse vlaggen zodat de template geen None-vergelijkingen hoeft te doen
        "unreachable": (afstand_ly is None) if jf else (jumps is None),
        "negative": net is not None and net < 0,
        "cost": cost,
        "cost_fmt": fmt_isk(cost) if cost is not None else "?",
        "net": net,
        "net_fmt": fmt_isk(net) if net is not None else "?",
        "per_jump": per_jump,
        "per_jump_fmt": fmt_isk(per_jump) if per_jump is not None else "?",
        "per_m3": reward / volume if volume else None,
        "per_m3_fmt": fmt_isk(reward / volume) if volume else "?",
        "days_to_complete": contract.get("days_to_complete"),
        "date_expired": _parse_date(contract.get("date_expired")),
        "date_issued": _parse_date(contract.get("date_issued")),
    }



# Sorteer-sleutels: None telt als "slechtst", zodat onbereikbare routes onderaan komen.
SORTS = {
    "net": (lambda r: (r["net"] is not None, r["net"] or 0), True),
    "reward": (lambda r: r["reward"], True),
    "per_jump": (lambda r: (r["per_jump"] is not None, r["per_jump"] or 0), True),
    "jumps": (lambda r: (r["jumps"] is None, r["jumps"] or 0), False),
    "volume": (lambda r: r["volume"], True),
    "expires": (lambda r: (r["date_expired"] is not None,
                           r["date_expired"] or datetime.max.replace(tzinfo=dt_timezone.utc)), False),
}


def sort_rows(rows, key):
    """Sorteer de regels op een van de SORTS-sleutels (default: netto winst)."""
    keyfunc, reverse = SORTS.get(key, SORTS["net"])
    return sorted(rows, key=keyfunc, reverse=reverse)


def build(contracts, isk_per_jump, min_reward=0, sort="net", route_voorkeur="kort",
          cfg=None, par=None):
    """Ruwe ESI-contracten → gesorteerde, verrijkte regels + samenvattende totalen."""
    rows = [
        enrich(c, isk_per_jump, route_voorkeur, cfg, par)
        for c in contracts
        if float(c.get("reward") or 0) >= min_reward
    ]
    rows = sort_rows(rows, sort)

    reachable = [r for r in rows if r["net"] is not None]
    totals = {
        "count": len(rows),
        "reward_fmt": fmt_isk(sum(r["reward"] for r in rows)),
        "net_fmt": fmt_isk(sum(r["net"] for r in reachable)),
        "collateral_fmt": fmt_isk(sum(r["collateral"] for r in rows)),
        "best_fmt": fmt_isk(max((r["net"] for r in reachable), default=0)),
    }
    return rows, totals
