"""Admin — Corp Hauling instellingen (singleton)."""

from django.contrib import admin
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from .forms import CorpFitForm, PilootAdminForm
from .models import Config, CorpFit, Piloot, Schip


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ("label", "corp_id", "kosten_model", "route_voorkeur", "isk_per_jump")
    fieldsets = (
        (None, {"fields": ("corp_id", "corp_name", "min_reward", "cache_minutes")}),
        (_("Kosten"), {"fields": ("kosten_model",)}),
        (_("Over gates"), {"fields": ("route_voorkeur", "isk_per_jump")}),
        (_("Jump freighter"), {"fields": ("jf_bereik_ly", "jf_isotopen_per_ly",
                                          "jf_brandstof_skill", "jf_isotoop_type_id",
                                          "jf_isotoop_prijs")}),
    )

    @admin.display(description=_("Instellingen"))
    def label(self, obj):
        return obj.corp_name or "⚙ Corp Hauling — klik om in te stellen"

    def save_model(self, request, obj, form, change):
        if obj.corp_id and not obj.corp_name:
            from .esi import resolve_names

            obj.corp_name = resolve_names([obj.corp_id]).get(obj.corp_id, "")
        super().save_model(request, obj, form, change)
        cache.delete(f"cc_contracts_{obj.corp_id}")

    @admin.display(description=_("Signaal"))
    def signaal(self, obj):
        """Waar loopt het mis? Hiermee zie je in één blik wie hulp nodig heeft."""
        par = self._par(obj)
        if not par:
            return "⚠ niet door te rekenen"
        if par.get("skill_bron") == "geen":
            # Geen (geldig) token met de skills-scope: er wordt met niveau 0
            # gerekend, en dat ziet de piloot zelf niet zomaar.
            return "⚠ geen skill-token"
        if not par.get("hold"):
            return "⚠ scheepsdata niet geladen"
        return "✓"

    def _can(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "corphauling.manage_settings"
        )

    def has_view_permission(self, request, obj=None):
        return self._can(request)

    def has_add_permission(self, request):
        return self._can(request) and not Config.objects.exists()

    def has_change_permission(self, request, obj=None):
        return self._can(request)

    def has_delete_permission(self, request, obj=None):
        return self._can(request)


@admin.register(Piloot)
class PilootAdmin(admin.ModelAdmin):
    """Overzicht van alle haul-profielen: wie vliegt wat, en waarmee we rekenen."""

    list_display = ("gebruiker", "character", "schip", "schepen_aantal", "skills",
                    "skills_bron", "bereik", "verbruik", "hold", "signaal")
    list_filter = ("schepen__schip_type_id",)
    search_fields = ("user__username", "user__profile__main_character__character_name")
    form = PilootAdminForm
    fields = ("user",)
    inlines = ()   # wordt onderaan gezet, zodat SchipInline eerst bestaat
    # Gebruiker-keuze via PilootAdminForm (nette dropdown). Bewust GÉÉN
    # autocomplete_fields/raw_id_fields: die eisen een geregistreerde User-admin
    # met search_fields, en die heeft Alliance Auth niet — autocomplete geeft dan
    # systeemcheck E039 (site start niet), raw_id een niet-werkende popup.

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def _par(self, obj):
        """Doorgerekende waarden voor deze piloot (gecached; nooit fataal)."""
        from .piloot import parameters

        try:
            return parameters(obj.user)
        except Exception:  # noqa: BLE001 — een overzicht mag nooit crashen op ESI
            return {}

    @admin.display(description=_("Gebruiker"), ordering="user__username")
    def gebruiker(self, obj):
        return obj.user.username

    @admin.display(description=_("Main"))
    def character(self, obj):
        main = getattr(getattr(obj.user, "profile", None), "main_character", None)
        return main.character_name if main else "—"

    @admin.display(description=_("Actief schip"))
    def schip(self, obj):
        s = obj.actief_schip()
        return str(s) if s else "—"

    @admin.display(description=_("Schepen"))
    def schepen_aantal(self, obj):
        return obj.schepen.count()

    @admin.display(description=_("Skills uit"), boolean=False)
    def skills_bron(self, obj):
        bron = self._par(obj).get("skill_bron")
        return {"esi": "EVE", "geen": _("niet gelezen"), "corp": _("corp")}.get(bron, "—")

    @admin.display(description=_("JDC / JFC / JF / ras"))
    def skills(self, obj):
        par = self._par(obj)
        if not par:
            return "—"
        return f"{par['jdc']} / {par['jfc']} / {par['jf_skill']} / {par['rassen_skill']}"

    @admin.display(description=_("Bereik"))
    def bereik(self, obj):
        par = self._par(obj)
        return f"{par['bereik_ly']:.1f} LY" if par.get("bereik_ly") else "—"

    @admin.display(description=_("Isotopen/LY"))
    def verbruik(self, obj):
        par = self._par(obj)
        return f"{par['isotopen_per_ly']:,.0f}".replace(",", ".") if par.get("isotopen_per_ly") else "—"

    @admin.display(description=_("Vrachtruimte"))
    def hold(self, obj):
        par = self._par(obj)
        return f"{par['hold']:,.0f} m³".replace(",", ".") if par.get("hold") else "—"

    @admin.display(description=_("Signaal"))
    def signaal(self, obj):
        """Waar loopt het mis? Hiermee zie je in één blik wie hulp nodig heeft."""
        par = self._par(obj)
        if not par:
            return "⚠ niet door te rekenen"
        if par.get("skill_bron") == "geen":
            # Geen (geldig) token met de skills-scope: er wordt met niveau 0
            # gerekend, en dat ziet de piloot zelf niet zomaar.
            return "⚠ geen skill-token"
        if not par.get("hold"):
            return "⚠ scheepsdata niet geladen"
        return "✓"

    def _can(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "corphauling.manage_settings"
        )

    def has_view_permission(self, request, obj=None):
        return self._can(request)

    def has_add_permission(self, request):
        return self._can(request)

    def has_change_permission(self, request, obj=None):
        return self._can(request)

    def has_delete_permission(self, request, obj=None):
        return self._can(request)


class SchipInline(admin.TabularInline):
    """De schepen van een piloot, direct onder z'n profiel."""

    model = Schip
    extra = 0
    fields = ("corp_fit", "naam", "actief")
    classes = ("collapse",)


PilootAdmin.inlines = (SchipInline,)


@admin.register(Schip)
class SchipAdmin(admin.ModelAdmin):
    """Alle schepen over alle piloten heen — handig om fits te vergelijken."""

    list_display = ("eigenaar", "schip", "naam", "fit_naam", "actief")
    list_filter = ("schip_type_id", "actief")
    search_fields = ("piloot__user__username", "naam")
    raw_id_fields = ("piloot",)
    list_select_related = ("corp_fit",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("piloot__user")

    @admin.display(description=_("Piloot"), ordering="piloot__user__username")
    def eigenaar(self, obj):
        return obj.piloot.user.username

    @admin.display(description=_("Schip"), ordering="schip_type_id")
    def schip(self, obj):
        return obj.get_schip_type_id_display()

    @admin.display(description=_("Fit"), ordering="corp_fit__naam")
    def fit_naam(self, obj):
        return obj.corp_fit.naam if obj.corp_fit else _("(eigen fit)")

    def _can(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "corphauling.manage_settings"
        )

    def has_view_permission(self, request, obj=None):
        return self._can(request)

    def has_add_permission(self, request):
        return self._can(request)

    def has_change_permission(self, request, obj=None):
        return self._can(request)

    def has_delete_permission(self, request, obj=None):
        return self._can(request)


@admin.register(CorpFit)
class CorpFitAdmin(admin.ModelAdmin):
    """Standaardfits van de corp; leden kiezen die uit een lijst."""

    form = CorpFitForm
    list_display = ("naam", "schip", "modules", "vermenigvuldiger", "hold_max", "in_gebruik",
                    "volgorde")
    list_filter = ("schip_type_id",)
    fields = ("naam", "schip_type_id", "fit", "volgorde")

    def _fit(self, obj):
        """(vermenigvuldiger, modules) van deze fit — nooit fataal."""
        from .fit import cargo_multiplier, parse_eft

        try:
            return cargo_multiplier(parse_eft(obj.fit))
        except Exception:  # noqa: BLE001 — een overzicht mag niet omvallen op ESI
            return 1.0, []

    @admin.display(description=_("Modules"))
    def modules(self, obj):
        _mult, mods = self._fit(obj)
        return len(mods) or "⚠ geen"

    @admin.display(description=_("Cargo"))
    def vermenigvuldiger(self, obj):
        mult, _mods = self._fit(obj)
        return f"×{mult:.3f}"

    @admin.display(description=_("Hold bij max skills"))
    def hold_max(self, obj):
        """Wat dit oplevert met Jump Freighters V en de rassen-skill V."""
        from .esi import schip_stats

        try:
            basis = schip_stats(obj.schip_type_id).get("hold") or 0
        except Exception:  # noqa: BLE001
            return "—"
        if not basis:
            return "—"
        mult, _mods = self._fit(obj)
        hold = basis * 1.5 * 1.25 * mult          # JF V (+50%) en ras V (+25%)
        return f"{hold:,.0f} m³".replace(",", ".")

    @admin.display(description=_("In gebruik"))
    def in_gebruik(self, obj):
        return obj.schepen.count()

    @admin.display(description=_("Schip"), ordering="schip_type_id")
    def schip(self, obj):
        return obj.get_schip_type_id_display()

    def _can(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "corphauling.manage_settings"
        )

    def has_view_permission(self, request, obj=None):
        return self._can(request)

    def has_add_permission(self, request):
        return self._can(request)

    def has_change_permission(self, request, obj=None):
        return self._can(request)

    def has_delete_permission(self, request, obj=None):
        return self._can(request)
