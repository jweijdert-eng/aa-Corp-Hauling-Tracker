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
from .hauls import haul_stats, user_hauls


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
    """Wat de ingelogde piloot verdiende met afgeleverde koeriers-ritten."""
    if not has_char_contracts_token(_character_ids(request.user)):
        return render(request, "corphauling/hauls.html", {"no_token": True})

    hauls, _met = user_hauls(request.user)
    return render(request, "corphauling/hauls.html", {
        "hauls": hauls,
        "stats": haul_stats(hauls),
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
