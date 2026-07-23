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
        fields = ["operator", "aircraft", "start_date", "end_date"]
        labels = {
            "operator": _("Operator"),
            "aircraft": _("Aircraft"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
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
