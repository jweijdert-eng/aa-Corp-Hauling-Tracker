"""Models — Corp Hauling (alleen permissies; de tracker houdt niets in de DB)."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class General(models.Model):
    """Meta-model voor permissies."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", _("Kan de haul-verdiensten bekijken")),
        )
