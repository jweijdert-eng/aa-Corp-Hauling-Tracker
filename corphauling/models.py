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
    class Meta:
        default_permissions = ()
        verbose_name = _("piloot-profiel")
        verbose_name_plural = _("piloot-profielen")

    def __str__(self) -> str:
        return f"{self.user}"

    def actief_schip(self):
        """Het schip waarmee gerekend wordt (expliciet gekozen, anders het eerste)."""
        return (self.schepen.filter(actief=True).first()
                or self.schepen.order_by("id").first())


class Schip(models.Model):
    """Eén jump freighter van een piloot, met z'n eigen fit.

    Iemand kan er meerdere hebben — bijvoorbeeld een Ark voor de kleine runs en
    een Rhea voor het grote werk — en kiest welke actief is.
    """

    piloot = models.ForeignKey(Piloot, on_delete=models.CASCADE, related_name="schepen")
    schip_type_id = models.IntegerField(
        choices=Piloot.SCHEPEN, default=28850, verbose_name=_("Schip"),
        help_text=_("Bepaalt het isotopenverbruik, de brandstofsoort en hoeveel er in past."),
    )
    naam = models.CharField(
        max_length=60, blank=True, default="", verbose_name=_("Eigen naam"),
        help_text=_("Optioneel, bijvoorbeeld \"grote hauler\" — handig als je er meerdere hebt."),
    )
    fit = models.TextField(
        blank=True, default="", verbose_name=_("Fit (plakken uit EVE)"),
        help_text=_("Plak je fit zoals je die in EVE kopieert. Modules die de vrachtruimte "
                    "vergroten tellen mee, mét stacking-penalty. Leeg = kale romp."),
    )
    hold_handmatig = models.FloatField(
        default=0, verbose_name=_("Vrachtruimte zelf invullen (m³)"),
        help_text=_("0 = uitrekenen uit schip, skills en fit. Vul het getal uit de game "
                    "in als je zeker wilt weten dat het klopt — dat gaat altijd voor."),
    )
    actief = models.BooleanField(
        default=False, verbose_name=_("Actief"),
        help_text=_("Met dit schip wordt op het contractenbord gerekend."),
    )

    class Meta:
        default_permissions = ()
        verbose_name = _("schip")
        verbose_name_plural = _("schepen")
        ordering = ("-actief", "id")

    def __str__(self) -> str:
        return self.naam or self.get_schip_type_id_display()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.actief:      # maar één schip tegelijk actief
            Schip.objects.filter(piloot=self.piloot).exclude(pk=self.pk).update(actief=False)


class CorpFit(models.Model):
    """Een standaardfit die de corp klaarzet, zodat leden niets hoeven te plakken."""

    naam = models.CharField(
        max_length=80, verbose_name=_("Naam"),
        help_text=_("Zoals leden 'm in de keuzelijst zien, bijv. \"Rhea — ORE\"."),
    )
    schip_type_id = models.IntegerField(
        choices=Piloot.SCHEPEN, verbose_name=_("Schip"),
        help_text=_("Voor welk schip deze fit bedoeld is."),
    )
    fit = models.TextField(
        verbose_name=_("Fit"),
        help_text=_("Het EFT-blok zoals je het uit EVE kopieert."),
    )
    volgorde = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Volgorde"),
        help_text=_("Lager staat hoger in de lijst."),
    )

    class Meta:
        default_permissions = ()
        verbose_name = _("corp-fit")
        verbose_name_plural = _("corp-fits")
        ordering = ("volgorde", "naam")

    def __str__(self) -> str:
        return self.naam
