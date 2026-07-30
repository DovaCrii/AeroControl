from pathlib import Path

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import Alert, AlertRule, Document, DocumentType
from .security import scan_uploaded_file
from .watchables import (
    WATCHABLE_MODELS,
    entity_type_choices,
    field_choices_for,
    resolve_model,
    watchable_fields,
)

DOCUMENTABLE_MODELS = {
    ("registry", "aircraft"),
    ("registry", "operator"),
    ("registry", "qualification"),
    ("operations", "flightpermission"),
    ("maintenance", "maintenancerecord"),
}

# Accepted uploads and the magic bytes each one must actually start with, so a
# renamed executable cannot pass as a document. KMZ is the flight-area export
# from Google Earth: a ZIP holding a KML, hence the same signature as DOCX.
# Plain KML is XML, which may or may not carry the declaration, so both openings
# are accepted.
ALLOWED_UPLOAD_SIGNATURES = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "kmz": (b"PK\x03\x04",),
    "kml": (b"<?xml", b"<kml", b"\xef\xbb\xbf<?xml", b"\xef\xbb\xbf<kml"),
}

DOCUMENTABLE_MODEL_LABELS = {
    ("registry", "aircraft"): _("Aircraft record"),
    ("registry", "operator"): _("Operator record"),
    ("registry", "qualification"): _("Qualification"),
    ("operations", "flightpermission"): _("Flight permission"),
    ("maintenance", "maintenancerecord"): _("Maintenance record"),
}


class DocumentForm(AeroModelForm):
    # LV-2: free-text titles drifted (same document type worded differently
    # session to session). Optional here; clean() fills it in from the
    # document type, the related record and the issue date when left blank,
    # so the common case needs no typing and stays consistent.
    title = forms.CharField(
        required=False,
        label=_("Title"),
        help_text=_(
            "Leave blank to generate it from the document type, "
            "the related record and the issue date."
        ),
    )
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
            "notes",
        )
        labels = {
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
        # LV-1: an empty catalog makes the required "Document type" field look
        # broken (nothing to pick). Point at where to fix it instead of
        # leaving the picker to speak for itself.
        if not DocumentType.objects.filter(is_active=True).exists():
            self.fields["doc_type"].help_text = _(
                "No document types configured yet. Create one first."
            )

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
            record = (
                model._default_manager.filter(pk=object_id, is_active=True).first()
                if model is not None
                else None
            )
            if record is None:
                self.add_error("object_id", _("Select an active existing record."))
            elif not cleaned.get("title"):
                cleaned["title"] = self._autogenerate_title(
                    record, cleaned.get("doc_type"), cleaned.get("issue_date")
                )

        uploaded = cleaned.get("file")
        if uploaded:
            extension = Path(uploaded.name).suffix.lower().lstrip(".")
            if extension not in ALLOWED_UPLOAD_SIGNATURES:
                self.add_error(
                    "file",
                    # Built from the same mapping that validates the content, so
                    # the message cannot claim to accept something we reject.
                    _("Allowed file types: %(types)s.")
                    % {
                        "types": ", ".join(
                            sorted(e.upper() for e in ALLOWED_UPLOAD_SIGNATURES)
                        )
                    },
                )
            elif uploaded.size > 20 * 1024 * 1024:
                self.add_error("file", _("The maximum file size is 20 MB."))
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
            self.add_error(
                "expiry_date", _("This document type requires an expiry date.")
            )
        return cleaned

    @staticmethod
    def _autogenerate_title(record, doc_type, issue_date):
        parts = [str(doc_type)] if doc_type else []
        parts.append(str(record))
        if issue_date:
            parts.append(issue_date.isoformat())
        return " · ".join(parts)[:200]

    @staticmethod
    def _validate_file_signature(uploaded, extension):
        signatures = ALLOWED_UPLOAD_SIGNATURES[extension]
        current_position = uploaded.tell()
        uploaded.seek(0)
        header = uploaded.read(16)
        uploaded.seek(current_position)
        if not any(header.startswith(signature) for signature in signatures):
            raise forms.ValidationError(
                _("The uploaded file content does not match its extension.")
            )

    def save(self, commit=True):
        document = super().save(commit=False)
        document.content_type = self.cleaned_data["entity_type"]
        if commit:
            document.save()
        return document


class DocumentTypeForm(AeroModelForm):
    class Meta:
        model = DocumentType
        fields = ["name", "code", "requires_expiry", "is_insurance"]


class AlertRuleForm(AeroModelForm):
    """Both fields are pickers, not free text.

    field_to_watch depends on the chosen entity, so its options are narrowed to
    that model once one is selected (on a bound form or when editing); before
    that it offers every watchable field and the model's clean() rejects a
    mismatch.
    """

    entity_type = forms.ChoiceField(
        choices=[("", "---------")] + entity_type_choices(),
        label=_("Entity type"),
    )
    field_to_watch = forms.ChoiceField(choices=[], label=_("Field to watch"))

    class Meta:
        model = AlertRule
        fields = [
            "name",
            "entity_type",
            "field_to_watch",
            "days_before_expiry",
            "enabled",
            "create_kanban_task",
            "target_board",
            "target_stage",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected = self.data.get("entity_type") or self.initial.get("entity_type")
        if not selected and self.instance and self.instance.pk:
            selected = self.instance.entity_type
        options = field_choices_for(selected) if selected else self._all_field_choices()
        self.fields["field_to_watch"].choices = [("", "---------")] + options

    @staticmethod
    def _all_field_choices():
        names = []
        for key in WATCHABLE_MODELS:
            for name in watchable_fields(resolve_model(key)):
                if name not in names:
                    names.append(name)
        return [(name, name) for name in sorted(names)]


class AlertForm(AeroModelForm):
    class Meta:
        model = Alert
        fields = ["alert_rule", "content_type", "object_id", "message"]
