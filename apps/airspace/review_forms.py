"""The correction form of the AIP review (LV-361, phase 4).

Not a `ModelForm` with `__all__`: a person may change the outline (vertices) and three texts of a
zone, nothing else, and every rule lives in `aip_review` so the form, the service and any future
caller share it.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from . import aip_review

TEXT_FIELDS = ("lateral_text", "vertical_limits_text", "schedule_text")


class CorrectionForm(forms.Form):
    vertices = forms.CharField(
        label=_("Vertices (one per line: latitude, longitude)"),
        required=False,
        max_length=60_000,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "class": "form-control font-monospace",
                "spellcheck": "false",
            }
        ),
        help_text=_(
            "Decimal degrees (-33.4569, -70.6483) or degrees, minutes and seconds. "
            "Put them in order around the outline; the polygon must not cross itself."
        ),
    )
    lateral_text = forms.CharField(
        label=_("Lateral limits"),
        required=False,
        max_length=20_000,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
    )
    vertical_limits_text = forms.CharField(
        label=_("Vertical limits"),
        required=False,
        max_length=2_000,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )
    schedule_text = forms.CharField(
        label=_("Remarks and schedule"),
        required=False,
        max_length=20_000,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        help_text=_("Phones, e-mails and names with a title are removed when saving."),
    )

    def __init__(self, *args, feature, **kwargs):
        self.feature = feature
        initial = {name: getattr(feature, name) for name in TEXT_FIELDS}
        initial["vertices"] = aip_review.vertices_text(feature)
        kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)

    def clean_vertices(self):
        text = self.cleaned_data["vertices"].strip()
        if text == aip_review.vertices_text(self.feature).strip():
            return None  # untouched: the geometry stays as it is
        if not text:
            return None
        return aip_review.parse_vertices(text)

    def texts(self):
        return {name: self.cleaned_data[name] for name in TEXT_FIELDS}
