from django import forms
from .models import FlightPermission, FlightRecord
FlightPermissionForm=type("FlightPermissionForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":FlightPermission,"fields":"__all__"})})
FlightRecordForm=type("FlightRecordForm",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":FlightRecord,"fields":"__all__"})})
