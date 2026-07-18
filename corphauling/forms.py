"""Formulieren — Corp Hauling."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Piloot


class PilootForm(forms.ModelForm):
    """Persoonlijk haul-profiel: schip en skills."""

    class Meta:
        model = Piloot
        fields = ("schip_type_id", "skills_uit_esi", "jdc", "jfc", "jf_skill",
                  "rassen_skill", "fit", "hold_handmatig")
        widgets = {
            "schip_type_id": forms.Select(attrs={"class": "form-select"}),
            "skills_uit_esi": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "jdc": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "jfc": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "jf_skill": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "rassen_skill": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "fit": forms.Textarea(attrs={
                "class": "form-control", "rows": 8,
                "placeholder": (
                    "[Rhea, mijn hauler]\n"
                    "Expanded Cargohold II\n"
                    "Expanded Cargohold II\n"
                    "Expanded Cargohold II"
                ),
            }),
            "hold_handmatig": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1000}),
        }

    def clean_jdc(self):
        return min(5, max(0, self.cleaned_data["jdc"]))

    def clean_jfc(self):
        return min(5, max(0, self.cleaned_data["jfc"]))

    def clean_jf_skill(self):
        return min(5, max(0, self.cleaned_data["jf_skill"]))

    def clean_rassen_skill(self):
        return min(5, max(0, self.cleaned_data["rassen_skill"]))
