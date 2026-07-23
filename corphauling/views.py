"""Views — Corp Hauling verdiensten-tracker."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from esi.decorators import token_required

from .esi import CHAR_CONTRACTS_SCOPE, has_char_contracts_token
from .hauls import (
    capture_hauls, demo_hauls, fmt_isk, haul_history, haul_stats, user_hauls,
)
from .models import Instellingen


def _character_ids(user):
    try:
        from allianceauth.eveonline.models import EveCharacter

        return list(EveCharacter.objects.filter(character_ownership__user=user)
                    .values_list("character_id", flat=True))
    except Exception:  # noqa: BLE001
        return []


@login_required
@permission_required("corphauling.basic_access")
def index(request: WSGIRequest) -> HttpResponse:
    """Haul-verdiensten, per maand — met een historie die zich opbouwt."""
    demo = Instellingen.get().demo_modus
    heeft_token = has_char_contracts_token(_character_ids(request.user))

    # Zonder token én zonder demo valt er niets te tonen → koppel-scherm.
    if not heeft_token and not demo:
        return render(request, "corphauling/hauls.html", {"no_token": True})

    # Live ophalen, de afgeronde ritten vastleggen, dan de historie per maand lezen.
    live = []
    if heeft_token:
        live, _met = user_hauls(request.user)
        capture_hauls(request.user, live)   # demo-ritten komen hier nooit langs
    maanden = haul_history(request.user)
    in_progress = [h for h in live if h["is_bezig"]]

    # Welke maand-tab is gekozen? Default = de nieuwste maand.
    keys = [m["key"] for m in maanden]
    gekozen = request.GET.get("maand")
    if gekozen not in keys:
        gekozen = keys[0] if keys else None

    actief = next((m for m in maanden if m["key"] == gekozen), None)
    op_nieuwste = not keys or gekozen == keys[0]
    # Lopende ritten horen bij 'nu', dus alleen op de nieuwste maand-tab tonen.
    onderweg = list(in_progress) if op_nieuwste else []
    voltooid = list(actief["hauls"]) if actief else []

    # Demo-ritten alleen op de nieuwste tab, vooraan, en nooit opgeslagen.
    if demo and op_nieuwste:
        d = demo_hauls()
        onderweg = [h for h in d if h["is_bezig"]] + onderweg
        voltooid = [h for h in d if not h["is_bezig"]] + voltooid

    onderweg_reward = sum(h["beloning"] for h in onderweg)

    return render(request, "corphauling/hauls.html", {
        "maanden": maanden,
        "gekozen": gekozen,
        "onderweg": onderweg,
        "voltooid": voltooid,
        "onderweg_totaal_fmt": fmt_isk(onderweg_reward),
        "stats": haul_stats(voltooid + onderweg),
        "demo": demo,
        "heeft_historie": bool(maanden),
    })


@login_required
@permission_required("corphauling.basic_access")
@token_required(scopes=[CHAR_CONTRACTS_SCOPE])
def koppel_contracts(request: WSGIRequest, token) -> HttpResponse:
    """Je character koppelen zodat we je afgeleverde ritten kunnen lezen."""
    cache.delete(f"cc_charcontracts_{token.character_id}")
    messages.success(
        request,
        _("%(naam)s is gekoppeld — je haul-verdiensten worden nu getoond.")
        % {"naam": token.character_name},
    )
    return redirect("corphauling:index")
