"""Models — Corp Hauling Tracker."""

from django.conf import settings
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


class Instellingen(models.Model):
    """Losse plugin-instellingen (één rij — singleton), te beheren in de admin."""

    demo_modus = models.BooleanField(
        default=False,
        help_text=_("Toon voorbeeld-ritten (met DEMO-label) om de weergave te bekijken."),
    )

    class Meta:
        default_permissions = ()
        verbose_name = _("Corp Hauling instelling")
        verbose_name_plural = _("Corp Hauling instellingen")

    def __str__(self) -> str:
        return "Corp Hauling instellingen"

    def save(self, *args, **kwargs):
        self.pk = 1                      # dwing één rij af → singleton
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Haul(models.Model):
    """Een afgeleverde (of gefaalde) koeriers-rit, bewaard voor de historie.

    ESI geeft maar ~30 dagen contracten terug, dus we leggen elke afgeronde rit
    vast zodra we 'm zien. Zo bouwt de maand-historie zich vanzelf op.
    """

    contract_id = models.BigIntegerField(unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="corphauling_hauls",
    )
    character_id = models.BigIntegerField()
    character_name = models.CharField(max_length=100, default="")

    reward = models.FloatField(default=0)
    volume = models.FloatField(default=0)
    collateral = models.FloatField(default=0)
    start_name = models.CharField(max_length=120, default="")
    end_name = models.CharField(max_length=120, default="")
    title = models.CharField(max_length=255, blank=True, default="")

    failed = models.BooleanField(default=False)     # False = netjes afgeleverd
    date_accepted = models.DateTimeField(null=True, blank=True)   # wanneer aangenomen
    date_completed = models.DateTimeField()
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ("-date_completed",)
        indexes = [models.Index(fields=["user", "date_completed"])]

    def __str__(self) -> str:
        return f"{self.character_name}: {self.start_name} → {self.end_name}"
