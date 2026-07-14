from django import forms
from .models import MaintenanceRecord,MaintenanceHistory
MaintenanceRecordForm=type("MaintenanceRecordForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":MaintenanceRecord,"fields":"__all__"})})
MaintenanceHistoryForm=type("MaintenanceHistoryForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":MaintenanceHistory,"fields":"__all__"})})
