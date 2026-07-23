"""Admin — Corp Hauling.

De verdiensten-tracker zelf houdt weinig in de database, maar de demo-schakelaar
staat hier zodat je 'm aan/uit kunt zetten.
"""

from django.contrib import admin

from .models import Instellingen


@admin.register(Instellingen)
class InstellingenAdmin(admin.ModelAdmin):
    """Eén rij met de plugin-instellingen; demo direct in de lijst te togglen."""

    list_display = ("__str__", "demo_modus")
    list_editable = ("demo_modus",)

    def has_add_permission(self, request):
        # Singleton: alleen toevoegen als er nog geen rij bestaat.
        return not Instellingen.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
