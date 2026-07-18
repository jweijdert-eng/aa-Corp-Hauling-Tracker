"""Formulieren — Corp Hauling."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CorpFit, Schip


class SchipForm(forms.ModelForm):
    """Eén jump freighter met z'n fit."""

    corp_fit = forms.ModelChoiceField(
        queryset=CorpFit.objects.all(), required=False,
        label=_("Corp-fit overnemen"), empty_label=_("— eigen fit hieronder —"),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_("Kies een standaardfit van de corp; die vult het veld hieronder. "
                    "Laat leeg als je je eigen fit plakt."),
    )

    field_order = ("schip_type_id", "naam", "corp_fit", "fit", "hold_handmatig")

    class Meta:
        model = Schip
        fields = ("schip_type_id", "naam", "fit", "hold_handmatig")
        widgets = {
            "schip_type_id": forms.Select(attrs={"class": "form-select"}),
            "naam": forms.TextInput(attrs={"class": "form-control",
                                           "placeholder": _("bijv. grote hauler")}),
            "fit": forms.Textarea(attrs={
                "class": "form-control", "rows": 7,
                "placeholder": (
                    "[Rhea, mijn hauler]\n"
                    "Expanded Cargohold II\n"
                    "Expanded Cargohold II\n"
                    "Expanded Cargohold II"
                ),
            }),
            "hold_handmatig": forms.NumberInput(attrs={"class": "form-control",
                                                       "min": 0, "step": 1000}),
        }

    def clean(self):
        """Een gekozen corp-fit wint van wat er in het tekstveld staat."""
        data = super().clean()
        corp_fit = data.get("corp_fit")
        if corp_fit:
            data["fit"] = corp_fit.fit
            self.instance.fit = corp_fit.fit
        return data
