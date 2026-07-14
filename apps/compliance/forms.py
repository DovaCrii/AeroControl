from django import forms
from .models import DocumentType, Document, AlertRule, Alert
for model in (DocumentType, Document, AlertRule, Alert):
    globals()[f"{model.__name__}Form"] = type(f"{model.__name__}Form", (forms.ModelForm,), {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})})
