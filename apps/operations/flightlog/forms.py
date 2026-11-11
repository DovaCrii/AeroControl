"""LV-431: el alta de un log de vuelo desde la sección «Flight logs» (centro, aeronave, archivo)."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from apps.core.tenancy import scope_queryset_to_tenant
from apps.registry.models import Aircraft, CostCenter

from ..models import FlightLogAnalysis, FlightPermission
from .adapters import DJI_NAME

MAX_LOG_BYTES = 50 * 1024 * 1024


class CostCenterFilteredSelect(forms.Select):
    """Un `<select>` cuyas opciones llevan `data-cc` (el centro al que pertenecen).

    Sólo es una comodidad: `flight-log-form.js` oculta las que no son del centro elegido. Sin JS
    el formulario ofrece todas y el servidor valida igual (`FlightLogAnalysis.clean`).
    """

    def __init__(self, *args, cost_center_of=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cost_center_of = cost_center_of or {}

    def create_option(self, name, value, label, selected, index, *args, **kwargs):
        option = super().create_option(
            name, value, label, selected, index, *args, **kwargs
        )
        centre = self.cost_center_of.get(str(value))
        if centre:
            option["attrs"]["data-cc"] = centre
        return option


class FlightLogUploadForm(AeroModelForm):
    """Centro de costo → aeronave → archivo `.TXT` → permiso DGAC opcional."""

    file = forms.FileField(label=_("Flight log file (.TXT)"))

    class Meta:
        model = FlightLogAnalysis
        fields = ["cost_center", "aircraft", "permission"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        centres = scope_queryset_to_tenant(
            CostCenter.objects.filter(is_active=True), user, "tenant_id"
        ).order_by("code")
        aircraft = scope_queryset_to_tenant(
            Aircraft.objects.filter(is_active=True), user, "tenant_id"
        ).order_by("registration")
        permits = scope_queryset_to_tenant(
            FlightPermission.objects.filter(is_active=True),
            user,
            "cost_center__tenant_id",
        ).order_by("-created_at")
        self.fields["cost_center"].queryset = centres
        self.fields["aircraft"].queryset = aircraft
        self.fields["permission"].queryset = permits
        # Obligatorios en el alta aunque la base los admita nulos (filas anteriores).
        for name in ("cost_center", "aircraft"):
            self.fields[name].required = True
        self.fields["cost_center"].label = _("Cost center")
        self.fields["aircraft"].label = _("Aircraft")
        self.fields["permission"].label = _("DGAC permit (optional)")
        self.fields["cost_center"].empty_label = _("Select a cost center")
        self.fields["aircraft"].empty_label = _("Select an aircraft")
        self.fields["permission"].empty_label = _("No permit")
        self.fields["aircraft"].widget = CostCenterFilteredSelect(
            cost_center_of={
                str(pk): str(cc)
                for pk, cc in aircraft.values_list("pk", "cost_center_id")
                if cc
            },
            attrs={"data-cc-follows": "id_cost_center", "class": "form-select"},
        )
        self.fields["permission"].widget = CostCenterFilteredSelect(
            cost_center_of={
                str(pk): str(cc)
                for pk, cc in permits.values_list("pk", "cost_center_id")
            },
            attrs={"data-cc-follows": "id_cost_center", "class": "form-select"},
        )
        self.fields["cost_center"].widget.attrs["class"] = "form-select"
        self.fields["file"].widget.attrs.update(
            {"class": "form-control", "accept": ".txt,text/plain"}
        )
        # Para que el widget de aeronaves vuelva a enlazar la opción elegida tras `choices`.
        self.fields["aircraft"].widget.choices = self.fields["aircraft"].choices
        self.fields["permission"].widget.choices = self.fields["permission"].choices

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = uploaded.name or ""
        if not name.lower().endswith(".txt"):
            raise forms.ValidationError(
                _("Upload the .TXT file of the flight log."), code="not_txt"
            )
        if uploaded.size > MAX_LOG_BYTES:
            raise forms.ValidationError(
                _("The file is too large (50 MB maximum)."), code="too_large"
            )
        if uploaded.size == 0:
            raise forms.ValidationError(_("The file is empty."), code="empty")
        if not DJI_NAME.match(name.replace("\\", "/").rsplit("/", 1)[-1]):
            raise forms.ValidationError(
                _(
                    "This does not look like a DJI flight log. The file name should be "
                    "DJIFlightRecord_….txt."
                ),
                code="not_dji",
            )
        return uploaded
