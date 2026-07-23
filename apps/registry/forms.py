from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import Aircraft, Assignment, CostCenter, Operator, Qualification


class CostCenterForm(AeroModelForm):
    class Meta:
        model = CostCenter
        fields = ["code", "name"]
        labels = {"code": _("Code"), "name": _("Name")}


class AircraftForm(AeroModelForm):
    class Meta:
        model = Aircraft
        fields = [
            "registration",
            "type",
            "model",
            "manufacturer",
            "year",
            "cost_center",
            "status",
        ]
        labels = {
            "registration": _("Registration"),
            "type": _("Type"),
            "model": _("Model"),
            "manufacturer": _("Manufacturer"),
            "year": _("Year"),
            "cost_center": _("Cost Center"),
            "status": _("Status"),
        }


class OperatorForm(AeroModelForm):
    class Meta:
        model = Operator
        fields = ["employee_id", "full_name", "email", "phone", "cost_center"]
        labels = {
            "employee_id": _("Employee ID"),
            "full_name": _("Full name"),
            "email": _("Email"),
            "phone": _("Phone"),
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
