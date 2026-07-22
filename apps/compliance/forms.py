from pathlib import Path

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import Alert, AlertRule, Document, DocumentType
from .security import scan_uploaded_file

DOCUMENTABLE_MODELS = {
    ("registry", "aircraft"),
    ("registry", "operator"),
    ("operations", "flightpermission"),
    ("maintenance", "maintenancerecord"),
}

DOCUMENTABLE_MODEL_LABELS = {
    ("registry", "aircraft"): _("Aircraft record"),
    ("registry", "operator"): _("Operator record"),
    ("operations", "flightpermission"): _("Flight permission"),
    ("maintenance", "maintenancerecord"): _("Maintenance record"),
}


class DocumentForm(forms.ModelForm):
    entity_type = forms.ModelChoiceField(
        queryset=ContentType.objects.none(),
        empty_label=_("Select an entity type"),
        label=_("Entity type"),
    )
    object_id = forms.ChoiceField(
        choices=(),
        label=_("Related record"),
        help_text=_("Select an entity type first."),
    )
    file = forms.FileField(required=True, label=_("File"))

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
        labels = {
            "title": _("Title"),
            "doc_type": _("Document type"),
            "file": _("File"),
            "issue_date": _("Issue date"),
            "expiry_date": _("Expiry date"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_type_filter = Q()
        for app_label, model in DOCUMENTABLE_MODELS:
            allowed_type_filter |= Q(app_label=app_label, model=model)
        self.fields["entity_type"].queryset = ContentType.objects.filter(
            allowed_type_filter
        ).order_by("app_label", "model")
        self.fields["entity_type"].label_from_instance = lambda content_type: (
            DOCUMENTABLE_MODEL_LABELS[(content_type.app_label, content_type.model)]
        )
        self.fields["entity_type"].widget.attrs.update(
            {
                "hx-get": reverse("document-entity-options"),
                "hx-trigger": "change",
                "hx-target": "#document-object-field",
                "hx-swap": "outerHTML",
            }
        )
        if self.instance and self.instance.pk and not self.instance._state.adding:
            self.fields["entity_type"].initial = self.instance.content_type
        raw_entity_type = self.data.get("entity_type") or self.initial.get(
            "entity_type"
        )
        if raw_entity_type:
            self._populate_object_choices(raw_entity_type)

    def _populate_object_choices(self, content_type_id):
        try:
            content_type = ContentType.objects.get(pk=content_type_id)
        except (ContentType.DoesNotExist, TypeError, ValueError):
            return
        if (content_type.app_label, content_type.model) not in DOCUMENTABLE_MODELS:
            return
        model = content_type.model_class()
        if model is None:
            return
        records = model._default_manager.filter(is_active=True).order_by("created_at")
        choices = [(str(record.pk), str(record)) for record in records]
        self.fields["object_id"].choices = choices
        self.fields["object_id"].help_text = (
            _("Select the operational record this document belongs to.")
            if choices
            else _("There are no active records of this type yet.")
        )

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
            elif uploaded.size > 20 * 1024 * 1024:
                self.add_error("file", "The maximum file size is 20 MB.")
            else:
                try:
                    self._validate_file_signature(uploaded, extension)
                except forms.ValidationError as exc:
                    self.add_error("file", exc)
                try:
                    scan_uploaded_file(uploaded)
                except RuntimeError as exc:
                    self.add_error("file", str(exc))
        doc_type = cleaned.get("doc_type")
        if doc_type and doc_type.requires_expiry and not cleaned.get("expiry_date"):
            self.add_error("expiry_date", "This document type requires an expiry date.")
        return cleaned

    @staticmethod
    def _validate_file_signature(uploaded, extension):
        signatures = {
            "pdf": (b"%PDF-",),
            "png": (b"\x89PNG\r\n\x1a\n",),
            "jpg": (b"\xff\xd8\xff",),
            "jpeg": (b"\xff\xd8\xff",),
            "docx": (b"PK\x03\x04",),
            "xlsx": (b"PK\x03\x04",),
        }
        current_position = uploaded.tell()
        uploaded.seek(0)
        header = uploaded.read(16)
        uploaded.seek(current_position)
        if not any(header.startswith(signature) for signature in signatures[extension]):
            raise forms.ValidationError(
                _("The uploaded file content does not match its extension.")
            )

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
