"""Models — Corp Hauling."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class General(models.Model):
    """Meta-model voor permissies."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", _("Kan de corp-hauling bekijken")),
            ("manage_settings", _("Kan de instellingen van Corp Hauling beheren")),
        )


class Config(models.Model):
    """Eén rij met instellingen (singleton), bewerkbaar via het admin-paneel."""

    corp_id = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("Corporation-id"),
        help_text=_("De EVE corporation-id waarvan de contracten getoond worden. "
                    "Laat leeg om de corp van het gekoppelde token te gebruiken."),
    )
    corp_name = models.CharField(
        max_length=100, blank=True, default="", verbose_name=_("Corporation-naam"),
        help_text=_("Wordt automatisch opgezocht bij opslaan; anders zelf invullen."),
    )
    MODEL_GATES = "gates"
    MODEL_JF = "jf"
    MODEL_KEUZES = [
        (MODEL_GATES, _("Over gates — kosten per sprong")),
        (MODEL_JF, _("Jump freighter — brandstof per lichtjaar")),
    ]

    kosten_model = models.CharField(
        max_length=10, choices=MODEL_KEUZES, default=MODEL_GATES,
        verbose_name=_("Kostenmodel"),
        help_text=_("Hoe de kosten van een contract berekend worden. Een jump "
                    "freighter vliegt niet over gates maar springt op afstand, "
                    "dus daar telt het aantal lichtjaren en de isotopen — niet "
                    "het aantal sprongen."),
    )
    jf_bereik_ly = models.FloatField(
        default=10.0, verbose_name=_("Sprongbereik (lichtjaar)"),
        help_text=_("Maximale sprongafstand van het schip. Een Ark/Anshar/Nomad/Rhea "
                    "heeft 5,0 LY basis; met Jump Drive Calibration loopt dat op. "
                    "Bepaalt alleen het gétoonde aantal sprongen, niet de brandstof."),
    )
    jf_isotopen_per_ly = models.FloatField(
        default=8800.0, verbose_name=_("Isotopen per lichtjaar"),
        help_text=_("Basisverbruik van het schip (uit EVE: 8.800 voor een jump "
                    "freighter). Skills worden hieronder apart verrekend."),
    )
    jf_brandstof_skill = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Jump Fuel Conservation (0-5)"),
        help_text=_("Elk niveau scheelt 10% brandstof. Op V betaal je dus de helft."),
    )
    jf_isotoop_type_id = models.IntegerField(
        default=16274, verbose_name=_("Isotoop-type"),
        help_text=_("Type-id van de brandstof: 16274 Helium (Amarr), 17887 Oxygen "
                    "(Gallente), 17888 Nitrogen (Caldari), 17889 Hydrogen (Minmatar)."),
    )
    jf_isotoop_prijs = models.FloatField(
        default=0, verbose_name=_("Isotoopprijs (ISK, 0 = Jita)"),
        help_text=_("Vaste prijs per isotoop. Laat op 0 om automatisch de "
                    "Jita-verkoopprijs te gebruiken."),
    )

    ROUTE_KORT = "kort"
    ROUTE_VEILIG = "veilig"
    ROUTE_KEUZES = [
        (ROUTE_KORT, _("Kortste route — wat een piloot meestal vliegt")),
        (ROUTE_VEILIG, _("Veilige route — highsec waar mogelijk")),
    ]

    route_voorkeur = models.CharField(
        max_length=10, choices=ROUTE_KEUZES, default=ROUTE_KORT,
        verbose_name=_("Route om mee te rekenen"),
        help_text=_("Met welke route de sprongen en kosten berekend worden. "
                    "De piloot kiest zelf zijn route, dus standaard rekenen we met "
                    "de kortste. Zet dit op 'veilig' als jullie highsec-only vliegen. "
                    "Het aantal sprongen van de andere route wordt er altijd bij getoond."),
    )
    isk_per_jump = models.BigIntegerField(
        default=20_000_000, verbose_name=_("Kosten per sprong (ISK)"),
        help_text=_("Geschatte kosten per sprong voor de piloot (brandstof, tijd, slijtage). "
                    "Netto winst = beloning − sprongen × dit bedrag. "
                    "Richtwaarde: ~20.000.000 voor een freighter."),
    )
    min_reward = models.BigIntegerField(
        default=0, verbose_name=_("Minimale beloning (ISK)"),
        help_text=_("Contracten met een lagere beloning worden verborgen. 0 = alles tonen."),
    )
    cache_minutes = models.PositiveSmallIntegerField(
        default=15, verbose_name=_("Verversen om de (minuten)"),
        help_text=_("Hoe lang de contractenlijst uit ESI gecached wordt."),
    )

    class Meta:
        default_permissions = ()
        verbose_name = _("instellingen")
        verbose_name_plural = _("instellingen")

    def __str__(self) -> str:
        return "Corp Hauling instellingen"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "Config":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Piloot(models.Model):
    """Persoonlijk haul-profiel: met welk schip en welke skills iemand vliegt.

    Zonder profiel valt alles terug op de corp-instellingen in `Config`.
    """

    # De vier jump freighters. Bereik, verbruik, hold en brandstoftype komen
    # uit ESI (dogma) — hier staat alleen de keuze.
    SCHEPEN = [
        (28850, _("Ark (Amarr)")),
        (28848, _("Anshar (Gallente)")),
        (28846, _("Nomad (Minmatar)")),
        (28844, _("Rhea (Caldari)")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="corphauling_piloot",
    )
    schip_type_id = models.IntegerField(
        choices=SCHEPEN, default=28850, verbose_name=_("Schip"),
        help_text=_("Bepaalt het isotopenverbruik, de brandstofsoort en hoeveel er in je hold past."),
    )
    skills_uit_esi = models.BooleanField(
        default=True, verbose_name=_("Skills uit EVE halen"),
        help_text=_("Leest Jump Drive Calibration en Jump Fuel Conservation van je "
                    "character. Zet uit om ze hieronder zelf in te vullen."),
    )
    jdc = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Jump Drive Calibration"),
        help_text=_("+20% sprongbereik per niveau (5,0 LY basis → 10,0 LY op V)."),
    )
    jfc = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Jump Fuel Conservation"),
        help_text=_("−10% isotopenverbruik per niveau."),
    )
    jf_skill = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Jump Freighters"),
        help_text=_("+10% vrachtruimte en −10% brandstof per niveau."),
    )
    rassen_skill = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Freighter-skill van het ras"),
        help_text=_("Caldari/Gallente/Minmatar/Amarr Freighter: +5% vrachtruimte per niveau."),
    )
    fit = models.TextField(
        blank=True, default="", verbose_name=_("Fit (plakken uit EVE)"),
        help_text=_("Plak hier je fit zoals je die in EVE kopieert. Modules die de "
                    "vrachtruimte vergroten worden meegerekend, mét stacking-penalty. "
                    "Laat leeg voor een kale romp."),
    )
    hold_handmatig = models.FloatField(
        default=0, verbose_name=_("Vrachtruimte zelf invullen (m³)"),
        help_text=_("Staat dit op 0, dan rekenen we de vrachtruimte uit op basis van "
                    "je schip, skills en fit. Vul het getal uit de game in als je zeker "
                    "wilt weten dat het klopt — dan gaat deze waarde voor."),
    )

    class Meta:
        default_permissions = ()
        verbose_name = _("piloot-profiel")
        verbose_name_plural = _("piloot-profielen")

    def __str__(self) -> str:
        return f"{self.user} — {self.get_schip_type_id_display()}"
