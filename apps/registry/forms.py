from django import forms

from .models import Aircraft, Assignment, CostCenter, Operator, Qualification


class CostCenterForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = ["code", "name"]


class AircraftForm(forms.ModelForm):
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


class OperatorForm(forms.ModelForm):
    class Meta:
        model = Operator
        fields = ["employee_id", "full_name", "email", "phone", "cost_center"]


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["operator", "aircraft", "start_date", "end_date"]


class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = ["operator", "qualification_type", "issue_date", "expiry_date"]
