"""Admin — Corp Hauling instellingen (singleton)."""

from django.contrib import admin
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

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
        if obj.skills_uit_esi and par.get("skill_bron") != "esi":
            # Wel aangevinkt, maar we konden de skills niet lezen: meestal een
            # ontbrekend of verlopen token met de skills-scope.
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
    list_filter = ("skills_uit_esi", "schepen__schip_type_id")
    search_fields = ("user__username", "user__profile__main_character__character_name")
    fields = ("user", "skills_uit_esi", "jdc", "jfc", "jf_skill", "rassen_skill")
    inlines = ()   # wordt onderaan gezet, zodat SchipInline eerst bestaat
    # Bewust GEEN autocomplete_fields: dat eist een geregistreerde User-admin met
    # search_fields, en die heeft Alliance Auth niet. Django's systeemcheck (E039)
    # weigert dan te starten — de hele site ligt er dan uit.
    raw_id_fields = ("user",)

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
        return {"esi": "EVE", "profiel": _("profiel"), "corp": _("corp")}.get(bron, "—")

    @admin.display(description=_("JDC / JFC"))
    def skills(self, obj):
        par = self._par(obj)
        if not par:
            return f"{obj.jdc} / {obj.jfc}"
        # Wat er écht gebruikt wordt (bij 'skills uit EVE' kan dat afwijken
        # van wat er in het profiel staat).
        return f"{par['jdc']} / {par['jfc']}"

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
        if obj.skills_uit_esi and par.get("skill_bron") != "esi":
            # Wel aangevinkt, maar we konden de skills niet lezen: meestal een
            # ontbrekend of verlopen token met de skills-scope.
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
    fields = ("schip_type_id", "naam", "hold_handmatig", "actief", "fit")
    classes = ("collapse",)


PilootAdmin.inlines = (SchipInline,)


@admin.register(Schip)
class SchipAdmin(admin.ModelAdmin):
    """Alle schepen over alle piloten heen — handig om fits te vergelijken."""

    list_display = ("eigenaar", "schip", "naam", "actief", "hold_handmatig", "heeft_fit")
    list_filter = ("schip_type_id", "actief")
    search_fields = ("piloot__user__username", "naam")
    raw_id_fields = ("piloot",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("piloot__user")

    @admin.display(description=_("Piloot"), ordering="piloot__user__username")
    def eigenaar(self, obj):
        return obj.piloot.user.username

    @admin.display(description=_("Schip"), ordering="schip_type_id")
    def schip(self, obj):
        return obj.get_schip_type_id_display()

    @admin.display(description=_("Fit"), boolean=True)
    def heeft_fit(self, obj):
        return bool(obj.fit.strip())

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

    list_display = ("naam", "schip", "volgorde")
    list_filter = ("schip_type_id",)
    fields = ("naam", "schip_type_id", "fit", "volgorde")

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
