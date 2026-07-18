"""Views — Corp Hauling."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from esi.decorators import token_required

from .esi import (
    CONTRACTS_SCOPE,
    STRUCTURES_SCOPE,
    has_contracts_token,
    open_couriers,
    resolve_names,
)
from .forms import PilootForm
from .models import Config, Piloot
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

    return render(request, "corphauling/contracts.html", {
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
    """Je eigen haul-profiel: met welk schip en welke skills we rekenen."""
    piloot = Piloot.objects.filter(user=request.user).first()
    if request.method == "POST":
        form = PilootForm(request.POST, instance=piloot)
        if form.is_valid():
            nieuw = form.save(commit=False)
            nieuw.user = request.user
            nieuw.save()
            messages.success(request, _("Je profiel is opgeslagen."))
            return redirect("corphauling:profiel")
    else:
        form = PilootForm(instance=piloot)

    return render(request, "corphauling/profiel.html", {
        "form": form,
        "par": parameters(request.user),
        "heeft_profiel": piloot is not None,
    })
