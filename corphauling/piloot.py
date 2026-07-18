"""Van een gebruiker naar concrete rekenparameters.

Het profiel bepaalt met welk schip en welke skills gerekend wordt. Alles wat
niet uit een profiel komt valt terug op de corp-brede `Config`, zodat het bord
ook werkt voor wie niets heeft ingesteld.
"""

import logging

from .esi import SKILL_JDC, SKILL_JFC, character_skills, isotoop_prijs, schip_stats
from .models import Config, Piloot

logger = logging.getLogger(__name__)


def _characters(user):
    """De characters van een gebruiker, main eerst (die vliegt meestal)."""
    try:
        from allianceauth.eveonline.models import EveCharacter

        qs = EveCharacter.objects.filter(character_ownership__user=user)
        main = getattr(getattr(user, "profile", None), "main_character", None)
        chars = list(qs)
        if main:
            chars.sort(key=lambda c: c.character_id != main.character_id)
        return chars
    except Exception:  # noqa: BLE001 — geen AA-context of geen characters
        logger.debug("Characters van %s niet op te halen", user, exc_info=True)
        return []


def _skills_van_gebruiker(user):
    """(jdc, jfc, character_naam) — van het eerste character waar skills van zijn.

    We nemen de béste waarden die we vinden: als iemand meerdere characters
    heeft, vliegt hij het contract met degene die het kan.
    """
    beste = (None, None, None)
    for char in _characters(user):
        niveaus = character_skills(char.character_id)
        if not niveaus:
            continue
        jdc, jfc = niveaus.get(SKILL_JDC, 0), niveaus.get(SKILL_JFC, 0)
        if beste[0] is None or (jdc + jfc) > (beste[0] + beste[1]):
            beste = (jdc, jfc, char.character_name)
    return beste


def parameters(user=None):
    """Alle rekenparameters voor deze gebruiker.

    Geeft o.a. bereik in LY, isotopen per LY (na skills), isotoopprijs, de
    grootte van de hold en waar elk getal vandaan komt — dat laatste zodat de
    pagina eerlijk kan tonen waarop de berekening is gebaseerd.
    """
    cfg = Config.load()
    profiel = None
    if user is not None and user.is_authenticated:
        profiel = Piloot.objects.filter(user=user).first()

    # --- schip ---------------------------------------------------------
    if profiel:
        stats = schip_stats(profiel.schip_type_id)
    else:
        stats = None

    if stats and stats.get("isotopen_per_ly"):
        schip_naam = stats["naam"]
        bereik_basis = stats["bereik_basis"] or 5.0
        isotopen_basis = stats["isotopen_per_ly"]
        brandstof_id = stats["brandstof_type_id"] or cfg.jf_isotoop_type_id
        hold = stats["hold"] or None
        schip_bron = "profiel"
    else:
        # Geen profiel (of ESI gaf niets): corp-instellingen.
        schip_naam = ""
        bereik_basis = 5.0
        isotopen_basis = cfg.jf_isotopen_per_ly
        brandstof_id = cfg.jf_isotoop_type_id
        hold = None
        schip_bron = "corp"

    # --- skills --------------------------------------------------------
    char_naam = ""
    if profiel and profiel.skills_uit_esi:
        jdc, jfc, char_naam = _skills_van_gebruiker(user)
        skill_bron = "esi"
        if jdc is None:                      # geen token of geen skills gevonden
            jdc, jfc = profiel.jdc, profiel.jfc
            skill_bron = "profiel"
    elif profiel:
        jdc, jfc, skill_bron = profiel.jdc, profiel.jfc, "profiel"
    else:
        jdc, jfc, skill_bron = 5, cfg.jf_brandstof_skill, "corp"

    jdc = min(5, max(0, jdc or 0))
    jfc = min(5, max(0, jfc or 0))

    # --- afgeleide waarden ---------------------------------------------
    # JDC: +20% bereik per niveau. JFC: -10% verbruik per niveau.
    bereik = bereik_basis * (1 + 0.20 * jdc) if schip_bron == "profiel" else cfg.jf_bereik_ly
    isotopen_per_ly = isotopen_basis * (1 - 0.10 * jfc)
    prijs = cfg.jf_isotoop_prijs or isotoop_prijs(brandstof_id)

    return {
        "schip": schip_naam,
        "schip_bron": schip_bron,
        "bereik_ly": bereik,
        "isotopen_per_ly": isotopen_per_ly,
        "isotopen_basis": isotopen_basis,
        "brandstof_type_id": brandstof_id,
        "isotoop_prijs": prijs,
        "hold": hold,
        "jdc": jdc,
        "jfc": jfc,
        "skill_bron": skill_bron,
        "skill_character": char_naam,
        "heeft_profiel": profiel is not None,
    }
