"""Van een gebruiker naar concrete rekenparameters.

Het profiel bepaalt met welk schip en welke skills gerekend wordt. Alles wat
niet uit een profiel komt valt terug op de corp-brede `Config`, zodat het bord
ook werkt voor wie niets heeft ingesteld.
"""

import logging

from .esi import (RASSEN_SKILL, SKILL_JDC, SKILL_JFC, SKILL_JF,
                   character_skills, isotoop_prijs, schip_stats)
from .fit import hold_uit_fit
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


def _skills_van_gebruiker(user, rassen_skill_id):
    """(niveaus, character_naam) van het character dat het best kan haulen."""
    beste_niveaus, beste_naam, beste_score = None, "", -1
    for char in _characters(user):
        niveaus = character_skills(char.character_id)
        if not niveaus:
            continue
        score = (niveaus.get(SKILL_JDC, 0) + niveaus.get(SKILL_JFC, 0)
                 + niveaus.get(SKILL_JF, 0) + niveaus.get(rassen_skill_id, 0))
        if score > beste_score:
            beste_niveaus, beste_naam, beste_score = niveaus, char.character_name, score
    return beste_niveaus, beste_naam


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
    rassen_id = RASSEN_SKILL.get(profiel.schip_type_id if profiel else 0, 0)
    char_naam = ""
    if profiel and profiel.skills_uit_esi:
        niveaus, char_naam = _skills_van_gebruiker(user, rassen_id)
        if niveaus:
            jdc = niveaus.get(SKILL_JDC, 0)
            jfc = niveaus.get(SKILL_JFC, 0)
            jf_niv = niveaus.get(SKILL_JF, 0)
            rassen_niv = niveaus.get(rassen_id, 0)
            skill_bron = "esi"
        else:                                # geen token of geen skills gevonden
            jdc, jfc = profiel.jdc, profiel.jfc
            jf_niv, rassen_niv = profiel.jf_skill, profiel.rassen_skill
            skill_bron = "profiel"
    elif profiel:
        jdc, jfc = profiel.jdc, profiel.jfc
        jf_niv, rassen_niv = profiel.jf_skill, profiel.rassen_skill
        skill_bron = "profiel"
    else:
        jdc, jfc = 5, cfg.jf_brandstof_skill
        jf_niv, rassen_niv = 0, 0            # zonder profiel geen schip → geen bonussen
        skill_bron = "corp"

    begrens = lambda n: min(5, max(0, n or 0))
    jdc, jfc, jf_niv, rassen_niv = map(begrens, (jdc, jfc, jf_niv, rassen_niv))

    # --- afgeleide waarden ---------------------------------------------
    # Bereik : Jump Drive Calibration, +20% per niveau.
    # Verbruik: Jump Fuel Conservation −10% p/n én Jump Freighters −10% p/n.
    # Hold   : Jump Freighters +10% p/n én de rassen-freighterskill +5% p/n.
    bereik = bereik_basis * (1 + 0.20 * jdc) if schip_bron == "profiel" else cfg.jf_bereik_ly
    isotopen_per_ly = isotopen_basis * (1 - 0.10 * jfc) * (1 - 0.10 * jf_niv)
    prijs = cfg.jf_isotoop_prijs or isotoop_prijs(brandstof_id)

    hold_basis = hold
    hold_skills = hold * (1 + 0.10 * jf_niv) * (1 + 0.05 * rassen_niv) if hold else None

    fit_modules = []
    hold_berekend = hold_skills
    if hold_skills and profiel and profiel.fit.strip():
        hold_berekend, fit_modules = hold_uit_fit(hold_skills, profiel.fit)

    # Zelf ingevuld gaat altijd voor: dat is het enige getal dat we zeker weten.
    hold_bron = "berekend"
    if profiel and profiel.hold_handmatig:
        hold_berekend, hold_bron = profiel.hold_handmatig, "handmatig"
    elif fit_modules:
        hold_bron = "fit"

    return {
        "schip": schip_naam,
        "schip_bron": schip_bron,
        "bereik_ly": bereik,
        "isotopen_per_ly": isotopen_per_ly,
        "isotopen_basis": isotopen_basis,
        "brandstof_type_id": brandstof_id,
        "isotoop_prijs": prijs,
        "hold": hold_berekend,
        "hold_basis": hold_basis,
        "hold_skills": hold_skills,
        "hold_bron": hold_bron,
        "fit_modules": fit_modules,
        "jdc": jdc,
        "jfc": jfc,
        "jf_skill": jf_niv,
        "rassen_skill": rassen_niv,
        "isotopen_basis_kaal": isotopen_basis,
        "skill_bron": skill_bron,
        "skill_character": char_naam,
        "heeft_profiel": profiel is not None,
    }
