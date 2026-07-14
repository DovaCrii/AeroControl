from django import forms
from .models import CostCenter, Aircraft, Operator, Assignment, Qualification

class ModelForm(forms.ModelForm):
    class Meta:
        fields = "__all__"

for model in (CostCenter, Aircraft, Operator, Assignment, Qualification):
    globals()[f"{model.__name__}Form"] = type(f"{model.__name__}Form", (ModelForm,), {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})})
