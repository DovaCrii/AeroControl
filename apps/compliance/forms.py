from pathlib import Path
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.conf import settings
from .models import DocumentType, Document, AlertRule, Alert


class DocumentForm(forms.ModelForm):
    entity_type = forms.ModelChoiceField(queryset=ContentType.objects.none(), empty_label=None)
    file = forms.FileField(required=True)

    class Meta:
        model = Document
        fields = ("title", "doc_type", "entity_type", "object_id", "file", "issue_date", "expiry_date")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].queryset = ContentType.objects.exclude(app_label="contenttypes").order_by("app_label", "model")
        if self.instance and self.instance.pk:
            self.fields["entity_type"].initial = self.instance.content_type

    def clean(self):
        cleaned = super().clean()
        uploaded = cleaned.get("file")
        if uploaded:
            allowed = {"pdf", "docx", "xlsx", "png", "jpg", "jpeg"}
            extension = Path(uploaded.name).suffix.lower().lstrip(".")
            if extension not in allowed:
                self.add_error("file", "Only PDF, DOCX, XLSX, PNG, JPG, and JPEG files are allowed.")
            if uploaded.size > 20 * 1024 * 1024:
                self.add_error("file", "The maximum file size is 20 MB.")
        doc_type = cleaned.get("doc_type")
        if doc_type and doc_type.requires_expiry and not cleaned.get("expiry_date"):
            self.add_error("expiry_date", "This document type requires an expiry date.")
        return cleaned

    def save(self, commit=True):
        document = super().save(commit=False)
        document.content_type = self.cleaned_data["entity_type"]
        if commit:
            document.save()
        return document


for model in (DocumentType, AlertRule, Alert):
    globals()[f"{model.__name__}Form"] = type(f"{model.__name__}Form", (forms.ModelForm,), {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})})
