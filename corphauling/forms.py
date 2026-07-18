"""Formulieren — Corp Hauling."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CorpFit, Piloot, Schip


class PilootForm(forms.ModelForm):
    """Je skills — die gelden voor al je schepen."""

    class Meta:
        model = Piloot
        fields = ("skills_uit_esi", "jdc", "jfc", "jf_skill", "rassen_skill")
        widgets = {
            "skills_uit_esi": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "jdc": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "jfc": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "jf_skill": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "rassen_skill": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
        }

    def _begrens(self, veld):
        return min(5, max(0, self.cleaned_data[veld]))

    def clean_jdc(self):
        return self._begrens("jdc")

    def clean_jfc(self):
        return self._begrens("jfc")

    def clean_jf_skill(self):
        return self._begrens("jf_skill")

    def clean_rassen_skill(self):
        return self._begrens("rassen_skill")


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
