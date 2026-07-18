"""Formulieren — Corp Hauling."""

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CorpFit


class CorpFitForm(forms.ModelForm):
    """Corp-fit toevoegen: plak het EFT-blok, de rest leiden we eruit af."""

    class Meta:
        model = CorpFit
        fields = ("naam", "schip_type_id", "fit", "volgorde")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Beide zijn af te leiden uit de kopregel van de fit.
        self.fields["schip_type_id"].required = False
        self.fields["naam"].required = False
        self.fields["fit"].help_text = _(
            "Plak het blok zoals je het in EVE kopieert, inclusief de regel "
            "[Rhea, naam]. Schip en naam worden daaruit overgenomen als je ze "
            "hierboven leeg laat."
        )

    def clean(self):
        from .fit import cargo_multiplier, parse_eft
        from .models import Piloot

        data = super().clean()
        fit = (data.get("fit") or "").strip()
        if not fit:
            return data

        # Kopregel: [Rhea, ORE Expanded Cargohold]
        kop = re.match(r"^\s*\[([^,\]]+)(?:,\s*([^\]]*))?\]", fit)
        schip_naam = (kop.group(1).strip() if kop else "")
        fit_naam = (kop.group(2).strip() if kop and kop.group(2) else "")

        if not data.get("schip_type_id"):
            treffer = next((tid for tid, label in Piloot.SCHEPEN
                            if label.lower().startswith(schip_naam.lower())), None)
            if not treffer:
                raise forms.ValidationError(
                    _("Kon het schip niet uit de fit halen. Kies het hierboven, of zorg "
                      "dat de eerste regel begint met [Ark, ...], [Anshar, ...], "
                      "[Nomad, ...] of [Rhea, ...]."))
            data["schip_type_id"] = treffer

        if not data.get("naam"):
            label = dict(Piloot.SCHEPEN).get(data["schip_type_id"], "").split(" (")[0]
            data["naam"] = f"{label} — {fit_naam}" if fit_naam else label

        # Geen enkele cargo-module herkend? Dan levert de fit niets op.
        _mult, modules = cargo_multiplier(parse_eft(fit))
        if not modules:
            self.add_error("fit", _(
                "In deze fit staat geen module die de vrachtruimte vergroot. "
                "Kloppen de modulenamen? (Controleer de spelling zoals in EVE.)"))
        return data


class PilootAdminForm(forms.ModelForm):
    """Piloot toevoegen zonder de kapotte raw_id-popup.

    De gebruiker kies je uit een dropdown; bij het toevoegen worden alleen
    gebruikers getoond die nog géén profiel hebben (voorkomt de "bestaat al"-fout,
    want een profiel wordt ook automatisch aangemaakt zodra iemand z'n
    profielpagina opent).
    """

    class Meta:
        from .models import Piloot as _P
        model = _P
        fields = ("user",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        from .models import Piloot

        User = get_user_model()
        qs = User.objects.all()
        if self.instance and self.instance.pk:
            # Bewerken: alleen deze gebruiker tonen (user wijzig je niet).
            qs = User.objects.filter(pk=self.instance.user_id)
            self.fields["user"].disabled = True
        else:
            # Toevoegen: alleen wie nog geen profiel heeft.
            bezet = Piloot.objects.values_list("user_id", flat=True)
            qs = qs.exclude(pk__in=bezet)
        self.fields["user"].queryset = qs.select_related("profile__main_character").order_by("username")
        self.fields["user"].label_from_instance = self._label

    @staticmethod
    def _label(user):
        main = getattr(getattr(user, "profile", None), "main_character", None)
        return f"{user.username} — {main.character_name}" if main else user.username
