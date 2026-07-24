from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import Aircraft, Assignment, CostCenter, Operator, Qualification


class CostCenterForm(AeroModelForm):
    class Meta:
        model = CostCenter
        fields = ["code", "name", "responsible"]
        labels = {
            "code": _("Code"),
            "name": _("Name"),
            "responsible": _("Responsible"),
        }


class AircraftForm(AeroModelForm):
    class Meta:
        model = Aircraft
        fields = [
            "registration",
            "type",
            "model",
            "manufacturer",
            "year",
            "serial_number",
            "max_takeoff_weight_kg",
            "basic_weight_kg",
            "vlos",
            "parachute",
            "authorized_services",
            "cost_center",
            "status",
        ]
        labels = {
            "registration": _("Registration"),
            "type": _("Type"),
            "model": _("Model"),
            "manufacturer": _("Manufacturer"),
            "year": _("Year"),
            "serial_number": _("Serial number"),
            "max_takeoff_weight_kg": _("Maximum takeoff weight (kg)"),
            "basic_weight_kg": _("Basic weight (kg)"),
            "vlos": _("VLOS"),
            "parachute": _("Parachute"),
            "authorized_services": _("Authorized services"),
            "cost_center": _("Cost Center"),
            "status": _("Status"),
        }


class OperatorForm(AeroModelForm):
    class Meta:
        model = Operator
        fields = [
            "employee_id",
            "full_name",
            "email",
            "phone",
            "rut",
            "dgac_credential",
            "operator_type",
            "address",
            "authorizations",
            "cost_center",
        ]
        labels = {
            "employee_id": _("Employee ID"),
            "full_name": _("Full name"),
            "email": _("Email"),
            "phone": _("Phone"),
            "rut": _("RUT"),
            "dgac_credential": _("DGAC credential"),
            "operator_type": _("Operator type"),
            "address": _("Address"),
            "authorizations": _("Authorizations"),
            "cost_center": _("Cost Center"),
        }


class AssignmentForm(AeroModelForm):
    class Meta:
        model = Assignment
        fields = ["operator", "aircraft", "cost_center", "purpose", "start_date", "end_date", "status"]
        labels = {
            "operator": _("Operator"),
            "aircraft": _("Aircraft"),
            "cost_center": _("Cost center"),
            "purpose": _("Operation or purpose"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Assignment.STATUS_CHOICES are persisted in English-compatible codes,
        # but their labels must follow the active UI language.
        self.fields["status"].choices = [
            (value, _(label)) for value, label in Assignment.STATUS_CHOICES
        ]

    def clean(self):
        cleaned = super().clean()
        operator = cleaned.get("operator")
        aircraft = cleaned.get("aircraft")
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        status = cleaned.get("status")
        cost_center = cleaned.get("cost_center")
        if not operator or not aircraft or not start_date:
            return cleaned
        if status == "confirmed" and not cost_center:
            self.add_error(
                "cost_center",
                _("Una asignación confirmada requiere un centro de costo."),
            )
        end = end_date or start_date
        overlap = Assignment.objects.filter(
            is_active=True,
            operator=operator,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        overlap = overlap.filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date))
        if status == "confirmed" and overlap.filter(status="confirmed").exists():
            self.add_error("operator", _("El operador ya tiene una asignación confirmada en este período."))

        aircraft_overlap = Assignment.objects.filter(
            is_active=True,
            aircraft=aircraft,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        aircraft_overlap = aircraft_overlap.filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date))
        if status == "confirmed" and aircraft_overlap.filter(status="confirmed").exists():
            self.add_error("aircraft", _("La aeronave ya tiene una asignación confirmada en este período."))
        return cleaned


class QualificationForm(AeroModelForm):
    class Meta:
        model = Qualification
        fields = ["operator", "qualification_type", "issue_date", "expiry_date"]
        labels = {
            "operator": _("Operator"),
            "qualification_type": _("Qualification type"),
            "issue_date": _("Issue date"),
            "expiry_date": _("Expiry date"),
        }
