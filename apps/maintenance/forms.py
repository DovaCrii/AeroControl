from django import forms

from .models import MaintenanceHistory, MaintenanceRecord


class MaintenanceRecordForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = [
            "aircraft",
            "maintenance_type",
            "description",
            "scheduled_date",
            "performed_by",
            "cost",
        ]


class MaintenanceHistoryForm(forms.ModelForm):
    class Meta:
        model = MaintenanceHistory
        fields = ["record", "previous_status", "new_status", "changed_by"]


class MaintenanceCompletionForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["completed_date", "performed_by", "cost", "notes"]
