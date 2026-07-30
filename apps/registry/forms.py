from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import (
    Aircraft,
    AircraftAssignment,
    Assignment,
    CostCenter,
    Operator,
    OperatorAssignment,
    Qualification,
    QualificationType,
)


class CostCenterForm(AeroModelForm):
    class Meta:
        model = CostCenter
        fields = [
            "code",
            "name",
            "responsible",
            "responsible_operator",
            "responsible_contact_name",
            "responsible_contact_email",
        ]
        labels = {
            "code": _("Code"),
            "name": _("Name"),
            "responsible": _("Contract administrator name"),
            "responsible_operator": _("Responsible operator"),
            "responsible_contact_name": _("External contact name"),
            "responsible_contact_email": _("External contact email"),
        }
        help_texts = {
            "responsible_operator": _(
                "Recipient of expiry digests. Use when the responsible person "
                "is in the operator roster."
            ),
            "responsible_contact_name": _(
                "Use instead of the operator when the responsible person is "
                "external to the system (an administrator, secretary, or "
                "safety officer). Also used for the digest if the operator "
                "above has no reachable email."
            ),
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
            "current_location",
            "current_site",
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
            "current_location": _("Current location"),
            "current_site": _("Current site"),
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
        fields = [
            "operator",
            "aircraft",
            "cost_center",
            "purpose",
            "start_date",
            "end_date",
            "status",
        ]
        labels = {
            "operator": _("Operator"),
            "aircraft": _("Aircraft"),
            "cost_center": _("Cost center"),
            "purpose": _("Operation or purpose"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
        }

    # A previous __init__ here re-translated Assignment.STATUS_CHOICES at
    # runtime. That is no longer needed: the choices carry gettext_lazy labels
    # in the model, so the form picks up the active language on its own.
    # Verified identical output both ways before removing it.

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
                _("A confirmed assignment requires a cost center."),
            )
        end = end_date or start_date
        overlap = Assignment.objects.filter(
            is_active=True,
            operator=operator,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        overlap = overlap.filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if status == "confirmed" and overlap.filter(status="confirmed").exists():
            self.add_error(
                "operator",
                _("This operator already has a confirmed assignment in this period."),
            )

        aircraft_overlap = Assignment.objects.filter(
            is_active=True,
            aircraft=aircraft,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        aircraft_overlap = aircraft_overlap.filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if (
            status == "confirmed"
            and aircraft_overlap.filter(status="confirmed").exists()
        ):
            self.add_error(
                "aircraft",
                _("This aircraft already has a confirmed assignment in this period."),
            )
        return cleaned


class OperatorAssignmentForm(AeroModelForm):
    """OPS-1 per-resource assignment: an operator anchored to a cost center.

    No custom clean() needed here: ModelForm._post_clean() calls
    instance.full_clean(), which runs ResourceAssignment.clean() (the overlap
    check) automatically and attaches its errors to the right field.
    """

    class Meta:
        model = OperatorAssignment
        fields = [
            "operator",
            "cost_center",
            "start_date",
            "end_date",
            "status",
            "purpose",
        ]
        labels = {
            "operator": _("Operator"),
            "cost_center": _("Cost center"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
            "purpose": _("Operation or purpose"),
        }


class AircraftAssignmentForm(AeroModelForm):
    """OPS-1 per-resource assignment: an aircraft anchored to a cost center."""

    class Meta:
        model = AircraftAssignment
        fields = [
            "aircraft",
            "cost_center",
            "start_date",
            "end_date",
            "status",
            "purpose",
        ]
        labels = {
            "aircraft": _("Aircraft"),
            "cost_center": _("Cost center"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
            "purpose": _("Operation or purpose"),
        }


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # B4.3/LV-1 parity: an empty catalog makes the required picker look
        # broken. Point at where to create the first type.
        if not QualificationType.objects.filter(is_active=True).exists():
            self.fields["qualification_type"].help_text = _(
                "No qualification types configured yet. Create one first."
            )


class QualificationTypeForm(AeroModelForm):
    class Meta:
        model = QualificationType
        fields = ["name", "code", "model_keywords"]
