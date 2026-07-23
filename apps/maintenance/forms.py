from apps.core.forms import AeroModelForm
from .models import MaintenanceHistory, MaintenanceRecord


class MaintenanceRecordForm(AeroModelForm):
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


class MaintenanceHistoryForm(AeroModelForm):
    class Meta:
        model = MaintenanceHistory
        fields = ["record", "previous_status", "new_status", "changed_by"]


class MaintenanceCompletionForm(AeroModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["completed_date", "performed_by", "cost", "notes"]
