"""Views — Corp Hauling."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from esi.decorators import token_required

from .esi import (
    CHAR_CONTRACTS_SCOPE,
    CONTRACTS_SCOPE,
    SKILLS_SCOPE,
    STRUCTURES_SCOPE,
    has_contracts_token,
    open_couriers,
    resolve_names,
)
from .models import Config, CorpFit, Piloot, Schip
from .hauls import haul_stats, user_hauls
from .piloot import parameters, schepen_overzicht
from .profit import build

SORT_LABELS = [
    ("net", _("Netto winst")),
    ("per_jump", _("ISK per sprong")),
    ("reward", _("Beloning")),
    ("jumps", _("Sprongen")),
    ("volume", _("Volume")),
    ("expires", _("Verloopt")),
]


@login_required
@permission_required("corphauling.basic_access")
def index(request: WSGIRequest) -> HttpResponse:
    """Overzicht van de open koeriers-contracten met netto winst per contract."""
    cfg = Config.load()

    if not has_contracts_token():
        return render(request, "corphauling/contracts.html", {"no_token": True})

    sort = request.GET.get("sort", "net")
    force = request.GET.get("refresh") == "1"

    contracts, corp_id = open_couriers(
        cfg.corp_id, ttl=cfg.cache_minutes * 60, force=force
    )
    par = parameters(request.user)
    rows, totals = build(
        contracts,
        isk_per_jump=cfg.isk_per_jump,
        min_reward=cfg.min_reward,
        sort=sort,
        route_voorkeur=cfg.route_voorkeur,
        cfg=cfg,
        par=par,
    )

    # Namen van de uitgevers — plus die van de corp zelf — in één keer ophalen.
    # De corp-naam staat lang niet altijd in de config (of de corp komt van het
    # token), dus zoeken we 'm gewoon op i.p.v. een kaal id te tonen.
    wanted = [r["issuer_id"] for r in rows]
    if corp_id and not cfg.corp_name:
        wanted.append(corp_id)
    names = resolve_names(wanted)
    for row in rows:
        row["issuer"] = names.get(row["issuer_id"], f"#{row['issuer_id']}")

    corp_name = cfg.corp_name or names.get(corp_id) or (f"#{corp_id}" if corp_id else "")

    return render(request, "corphauling/contracts.html", {
        # Met de doorgerekende cijfers erbij, zodat de keuzelijst kan tonen
        # wat elk schip aankan.
        "mijn_schepen": schepen_overzicht(request.user),
        "rows": rows,
        "totals": totals,
        "sort": sort,
        "sorts": SORT_LABELS,
        "isk_per_jump": cfg.isk_per_jump,
        "route_voorkeur": cfg.route_voorkeur,
        "kosten_model": cfg.kosten_model,
        "par": par,
        "corp_id": corp_id,
        "corp_name": corp_name,
    })


@login_required
@permission_required("corphauling.manage_settings")
@token_required(scopes=[CONTRACTS_SCOPE, STRUCTURES_SCOPE])
def grant_access(request: WSGIRequest, token) -> HttpResponse:
    """Eenmalig een director-token koppelen; daarna verloopt het ophalen vanzelf."""
    cache.delete(f"cc_contracts_{Config.load().corp_id}")
    messages.success(
        request,
        _("Token gekoppeld voor %(name)s. De contracten worden nu automatisch opgehaald.")
        % {"name": token.character_name},
    )
    return redirect("corphauling:index")


@login_required
@permission_required("corphauling.basic_access")
def profiel(request: WSGIRequest) -> HttpResponse:
    """Je skills en je schepen. Schepen worden door een beheerder toegevoegd;
    hier kies je alleen met welke je vliegt."""
    piloot, _nieuw = Piloot.objects.get_or_create(user=request.user)

    if request.method == "POST" and request.POST.get("actie") == "schip-actief":
        schip = get_object_or_404(Schip, pk=request.POST.get("schip_id"), piloot=piloot)
        schip.actief = True
        schip.save()   # zet de andere automatisch uit
        messages.success(request, _("%(schip)s is nu je actieve schip.") % {"schip": schip})
        return redirect("corphauling:profiel")

    return render(request, "corphauling/profiel.html", {
        "schepen": schepen_overzicht(request.user),
        "par": parameters(request.user),
    })


@login_required
@permission_required("corphauling.basic_access")
def schip_wisselen(request: WSGIRequest) -> HttpResponse:
    """Vanaf het bord snel een ander schip actief maken."""
    if request.method == "POST":
        piloot = Piloot.objects.filter(user=request.user).first()
        schip = get_object_or_404(Schip, pk=request.POST.get("schip_id"), piloot=piloot)
        schip.actief = True
        schip.save()
    return redirect(request.POST.get("terug") or "corphauling:index")


@login_required
@permission_required("corphauling.basic_access")
@token_required(scopes=[SKILLS_SCOPE])
def koppel_skills(request: WSGIRequest, token) -> HttpResponse:
    """Je character koppelen zodat we je skills kunnen lezen."""
    cache.delete(f"cc_skills_{token.character_id}")
    messages.success(
        request,
        _("%(naam)s is gekoppeld — je skills worden nu gelezen.")
        % {"naam": token.character_name},
    )
    return redirect("corphauling:profiel")


@login_required
@permission_required("corphauling.basic_access")
def mijn_hauls(request: WSGIRequest) -> HttpResponse:
    """Wat de ingelogde piloot verdiende met afgeleverde koeriers-ritten."""
    from .esi import has_char_contracts_token

    chars = []
    try:
        from allianceauth.eveonline.models import EveCharacter
        chars = list(EveCharacter.objects.filter(character_ownership__user=request.user)
                     .values_list("character_id", flat=True))
    except Exception:  # noqa: BLE001
        pass

    if not has_char_contracts_token(chars):
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
    return redirect("corphauling:mijn_hauls")
