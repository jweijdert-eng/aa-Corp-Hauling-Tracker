"""Vrachtruimte uitrekenen uit een geplakte fit.

Werkt met het EFT-formaat dat je in EVE kopieert:

    [Rhea, mijn hauler]
    Expanded Cargohold II
    Expanded Cargohold II
    Expanded Cargohold II

Alleen modules die de cargo vergroten tellen mee; de rest wordt genegeerd.
"""

import logging
import re

from .esi import module_cargo_multiplier, resolve_type_ids

logger = logging.getLogger(__name__)

# EVE's stacking-penalty: de 2e en volgende gelijksoortige module werken minder
# hard door. Dit zijn de officiële factoren (exp(-(n/2.67)^2)).
STACKING = [1.0, 0.869119, 0.570583, 0.282955, 0.105992, 0.030189]


def parse_eft(tekst):
    """EFT-blok → lijst modulenamen (de shipnaam-regel en lege regels eruit)."""
    namen = []
    for regel in (tekst or "").splitlines():
        regel = regel.strip()
        if not regel or regel.startswith("["):        # [Rhea, naam] of [Empty ... slot]
            continue
        # "Expanded Cargohold II x3" of ", Charge Name" achter een module
        regel = regel.split(",")[0].strip()
        m = re.match(r"^(.*?)\s+x(\d+)$", regel)
        if m:
            namen.extend([m.group(1).strip()] * min(int(m.group(2)), 10))
        else:
            namen.append(regel)
    return [n for n in namen if n]


def cargo_multiplier(namen):
    """Totale vermenigvuldiger van deze modules, mét stacking-penalty.

    Geeft (multiplier, herkende_modules). Modules zonder cargo-bonus tellen niet
    mee en verschijnen dus ook niet in de lijst.
    """
    if not namen:
        return 1.0, []

    type_ids = resolve_type_ids(set(namen))
    bonussen = []
    for naam in namen:
        tid = type_ids.get(naam.lower())
        if not tid:
            continue
        mult = module_cargo_multiplier(tid)
        if mult and mult > 1:
            bonussen.append((naam, mult))

    # Sterkste module eerst: die krijgt de volle werking.
    bonussen.sort(key=lambda x: x[1], reverse=True)

    totaal = 1.0
    gebruikt = []
    for i, (naam, mult) in enumerate(bonussen):
        factor = STACKING[i] if i < len(STACKING) else 0.0
        effectief = 1 + (mult - 1) * factor
        totaal *= effectief
        gebruikt.append({"naam": naam, "bonus": mult, "effectief": effectief})
    return totaal, gebruikt


def hold_uit_fit(basis_hold, tekst):
    """Vrachtruimte na het toepassen van een geplakte fit.

    Geeft (hold, modules) — of (basis_hold, []) als er niets bruikbaars in staat.
    """
    namen = parse_eft(tekst)
    if not namen:
        return basis_hold, []
    mult, modules = cargo_multiplier(namen)
    return basis_hold * mult, modules
