from pathlib import Path

from django import forms
from django.contrib.contenttypes.models import ContentType

from .models import Alert, AlertRule, Document, DocumentType

DOCUMENTABLE_MODELS = {
    ("registry", "aircraft"),
    ("registry", "operator"),
    ("operations", "flightpermission"),
    ("maintenance", "maintenancerecord"),
}


class DocumentForm(forms.ModelForm):
    entity_type = forms.ModelChoiceField(
        queryset=ContentType.objects.none(), empty_label=None
    )
    file = forms.FileField(required=True)

    class Meta:
        model = Document
        fields = (
            "title",
            "doc_type",
            "entity_type",
            "object_id",
            "file",
            "issue_date",
            "expiry_date",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].queryset = ContentType.objects.filter(
            app_label__in={app for app, _ in DOCUMENTABLE_MODELS}
        ).order_by("app_label", "model")
        if self.instance and self.instance.pk:
            self.fields["entity_type"].initial = self.instance.content_type

    def clean(self):
        cleaned = super().clean()
        entity_type = cleaned.get("entity_type")
        object_id = cleaned.get("object_id")
        if (
            entity_type
            and (entity_type.app_label, entity_type.model) not in DOCUMENTABLE_MODELS
        ):
            self.add_error(
                "entity_type", "This entity type cannot receive compliance documents."
            )
        elif entity_type and object_id:
            model = entity_type.model_class()
            if (
                model is None
                or not model._default_manager.filter(
                    pk=object_id, is_active=True
                ).exists()
            ):
                self.add_error("object_id", "Select an active existing record.")

        uploaded = cleaned.get("file")
        if uploaded:
            allowed = {"pdf", "docx", "xlsx", "png", "jpg", "jpeg"}
            extension = Path(uploaded.name).suffix.lower().lstrip(".")
            if extension not in allowed:
                self.add_error(
                    "file",
                    "Only PDF, DOCX, XLSX, PNG, JPG, and JPEG files are allowed.",
                )
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


class DocumentTypeForm(forms.ModelForm):
    class Meta:
        model = DocumentType
        fields = ["name", "code", "requires_expiry"]


class AlertRuleForm(forms.ModelForm):
    class Meta:
        model = AlertRule
        fields = [
            "name",
            "entity_type",
            "field_to_watch",
            "days_before_expiry",
            "enabled",
        ]


class AlertForm(forms.ModelForm):
    class Meta:
        model = Alert
        fields = ["alert_rule", "content_type", "object_id", "message"]
