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
    CONTRACTS_SCOPE,
    SKILLS_SCOPE,
    STRUCTURES_SCOPE,
    has_contracts_token,
    open_couriers,
    resolve_names,
)
from .forms import SchipForm
from .models import Config, CorpFit, Piloot, Schip
from .piloot import parameters
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

    piloot = Piloot.objects.filter(user=request.user).first()
    return render(request, "corphauling/contracts.html", {
        "mijn_schepen": piloot.schepen.all() if piloot else [],
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
    """Je skills en je schepen — elk met een eigen fit; één is actief."""
    piloot, _nieuw = Piloot.objects.get_or_create(user=request.user)
    actie = request.POST.get("actie", "")

    if request.method == "POST" and actie in ("schip-nieuw", "schip-bewerk"):
        schip = None
        if actie == "schip-bewerk":
            schip = get_object_or_404(Schip, pk=request.POST.get("schip_id"), piloot=piloot)
        schip_form = SchipForm(request.POST, instance=schip)
        if schip_form.is_valid():
            nieuw_schip = schip_form.save(commit=False)
            nieuw_schip.piloot = piloot
            # Het eerste schip is meteen het actieve.
            if not piloot.schepen.exists():
                nieuw_schip.actief = True
            nieuw_schip.save()
            messages.success(request, _("Schip opgeslagen."))
            return redirect("corphauling:profiel")
    elif request.method == "POST" and actie == "schip-actief":
        schip = get_object_or_404(Schip, pk=request.POST.get("schip_id"), piloot=piloot)
        schip.actief = True
        schip.save()   # zet de andere automatisch uit
        messages.success(request, _("%(schip)s is nu je actieve schip.") % {"schip": schip})
        return redirect("corphauling:profiel")
    elif request.method == "POST" and actie == "schip-weg":
        schip = get_object_or_404(Schip, pk=request.POST.get("schip_id"), piloot=piloot)
        was_actief = schip.actief
        schip.delete()
        rest = piloot.schepen.first()
        if was_actief and rest:      # anders blijft er geen actief schip over
            rest.actief = True
            rest.save()
        messages.success(request, _("Schip verwijderd."))
        return redirect("corphauling:profiel")

    bewerk_id = request.GET.get("bewerk")
    bewerken = Schip.objects.filter(pk=bewerk_id, piloot=piloot).first() if bewerk_id else None

    return render(request, "corphauling/profiel.html", {
        "schip_form": SchipForm(instance=bewerken),
        "bewerken": bewerken,
        "schepen": piloot.schepen.all(),
        "par": parameters(request.user),
        "heeft_profiel": True,
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
