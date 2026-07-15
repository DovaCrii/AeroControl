from django import forms
from .models import MaintenanceRecord,MaintenanceHistory
MaintenanceRecordForm=type("MaintenanceRecordForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":MaintenanceRecord,"fields":"__all__"})})
MaintenanceHistoryForm=type("MaintenanceHistoryForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":MaintenanceHistory,"fields":"__all__"})})


class MaintenanceCompletionForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["completed_date", "performed_by", "cost", "notes"]
