"""Admin — Corp Hauling instellingen (singleton)."""

from django.contrib import admin
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from .models import Config


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
