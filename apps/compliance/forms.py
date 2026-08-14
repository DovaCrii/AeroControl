from pathlib import Path
from uuid import UUID

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.forms.models import ModelChoiceIterator
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import (
    Alert,
    AlertRule,
    Deliverable,
    Document,
    DocumentType,
    NonConformity,
)
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
    ("registry", "costcenter"),
    ("operations", "flightpermission"),
    ("maintenance", "maintenancerecord"),
    # Company-wide documents (AOC, procedures, forms) hang off the tenant.
    ("core", "operationaltenant"),
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

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def upload_errors(uploaded):
    """Every reason to refuse one uploaded file, as a list of messages.

    Extracted from `DocumentForm.clean` when LV-86 added the bulk upload: the
    two paths **must** apply the same guards, and a second copy is how one of
    them quietly ends up accepting a renamed executable. Returns the errors
    instead of raising so a batch can report file by file rather than dying on
    the first bad one.
    """
    errors = []
    extension = Path(uploaded.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_UPLOAD_SIGNATURES:
        # Built from the same mapping that validates the content, so the
        # message cannot claim to accept something we reject.
        return [
            _("Allowed file types: %(types)s.")
            % {"types": ", ".join(sorted(e.upper() for e in ALLOWED_UPLOAD_SIGNATURES))}
        ]
    if uploaded.size > MAX_UPLOAD_BYTES:
        return [_("The maximum file size is 20 MB.")]
    if not _signature_matches(uploaded, extension):
        errors.append(_("The uploaded file content does not match its extension."))
    try:
        scan_uploaded_file(uploaded)
    except RuntimeError as exc:
        errors.append(str(exc))
    return errors


def _signature_matches(uploaded, extension):
    """Whether the bytes start the way the extension promises."""
    signatures = ALLOWED_UPLOAD_SIGNATURES[extension]
    current_position = uploaded.tell()
    uploaded.seek(0)
    header = uploaded.read(16)
    uploaded.seek(current_position)
    return any(header.startswith(signature) for signature in signatures)


class CategorizedDocumentTypeIterator(ModelChoiceIterator):
    """The document-type options, as `<optgroup>`s in category order.

    LV-95: the picker was eighteen names in a flat list, ordered by whoever
    seeded them, so finding one meant reading all of them. Django renders a
    grouped option list when the iterator yields `(group_label, [choices])`,
    which is all this does.

    A type whose category is not a declared choice (a value left behind by a
    removed category) is **not** dropped -- it comes out under "Other". An
    option that silently disappears from a picker reads as a deleted document
    type, and the row it belongs to would become unselectable with nothing on
    screen saying why.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        grouped = {}
        for document_type in self.queryset:
            grouped.setdefault(document_type.category, []).append(
                self.choice(document_type)
            )
        for value, label in DocumentType.CATEGORY_CHOICES:
            options = grouped.pop(value, [])
            if value == DocumentType.CATEGORY_OTHER:
                # "Other" is declared last, so anything still ungrouped by now
                # has nowhere else to go.
                for orphans in grouped.values():
                    options.extend(orphans)
                grouped = {}
            if options:
                yield (label, options)


class CategorizedDocumentTypeChoiceField(forms.ModelChoiceField):
    """A document-type picker grouped by `DocumentType.category`."""

    iterator = CategorizedDocumentTypeIterator


def selectable_document_types(current_pk=None):
    """The types a picker may offer, newest classification order aside.

    Active types only -- an archived type means "stop filing under this".
    `current_pk` keeps the type a document already carries, so archiving a type
    never turns "replace this document" into an unfixable validation error on a
    field the person did not touch.
    """
    condition = Q(is_active=True)
    if current_pk:
        try:
            # `doc_type` can arrive from a URL parameter (DocumentCreate
            # prefills from GET), so it is not necessarily a valid key.
            condition |= Q(pk=UUID(str(current_pk)))
        except (AttributeError, TypeError, ValueError):
            pass
    return DocumentType.objects.filter(condition).order_by("name")


DOCUMENTABLE_MODEL_LABELS = {
    ("registry", "aircraft"): _("Aircraft record"),
    ("registry", "operator"): _("Operator record"),
    ("registry", "qualification"): _("Qualification"),
    ("registry", "costcenter"): _("Cost center"),
    ("operations", "flightpermission"): _("Flight permission"),
    ("maintenance", "maintenancerecord"): _("Maintenance record"),
    ("core", "operationaltenant"): _("Company"),
}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that keeps every selected file.

    Django's `FileField` deliberately returns only the last file of a multiple
    selection, so a `multiple` widget alone silently drops the rest -- the
    documented way to accept several is this pair (Django docs, "Uploading
    multiple files"). Each file is then validated on its own, so one bad file
    reports itself instead of failing the batch anonymously.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class DocumentBulkUploadForm(forms.Form):
    """LV-86: several files onto the same record, in one action.

    Deliberately **one record and one document type per batch**, not a free
    drop of unrelated files: the ambiguous case the user raised -- a file the
    system cannot attribute -- simply cannot arise here, because the person
    says up front what these belong to. That leaves the batch with only one
    real failure mode (a file that is not an acceptable document), which is
    reported per file rather than silently dropped.

    Titles are generated per file the same way `DocumentForm` does when the
    title is left blank, plus the file's own name to tell them apart -- twelve
    documents called "Póliza · RPA-5534 · 2026-08-04" would be worse than none.
    """

    entity_type = forms.ModelChoiceField(
        queryset=ContentType.objects.none(),
        empty_label=_("Select an entity type"),
        label=_("Entity type"),
    )
    object_id = forms.ChoiceField(choices=(), label=_("Related record"))
    doc_type = CategorizedDocumentTypeChoiceField(
        queryset=DocumentType.objects.none(), label=_("Document type")
    )
    files = MultipleFileField(
        label=_("Files"),
        help_text=_("Select several at once, or drop them here."),
    )
    issue_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label=_("Issue date")
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Expiry date"),
        help_text=_("Applied to every file in this batch."),
    )

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
        self.fields["doc_type"].queryset = selectable_document_types()
        # LV-94: the same HTMX wiring DocumentForm has. Without it this page
        # only worked when opened from a record's own file (which fills both
        # fields from the URL); reached any other way, "Related record" stayed
        # empty with no way to fill it. The endpoint returns the field by name,
        # so both forms can share it.
        self.fields["entity_type"].widget.attrs.update(
            {
                "hx-get": reverse("document-entity-options"),
                "hx-trigger": "change",
                "hx-target": "#document-object-field",
                "hx-swap": "outerHTML",
            }
        )
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
        self.fields["object_id"].choices = [
            (str(record.pk), str(record))
            for record in model._default_manager.filter(is_active=True).order_by(
                "created_at"
            )
        ]

    def clean(self):
        cleaned = super().clean()
        entity_type, object_id = cleaned.get("entity_type"), cleaned.get("object_id")
        if entity_type and object_id:
            model = entity_type.model_class()
            record = (
                model._default_manager.filter(pk=object_id, is_active=True).first()
                if model is not None
                else None
            )
            if record is None:
                self.add_error("object_id", _("Select an active existing record."))
            else:
                cleaned["record"] = record

        doc_type = cleaned.get("doc_type")
        if doc_type and doc_type.requires_expiry and not cleaned.get("expiry_date"):
            self.add_error(
                "expiry_date", _("This document type requires an expiry date.")
            )

        for uploaded in cleaned.get("files") or []:
            for error in upload_errors(uploaded):
                # Named, so a rejected file in a batch of twelve says which one.
                self.add_error(
                    "files",
                    _("%(name)s: %(error)s")
                    % {
                        "name": uploaded.name,
                        "error": error,
                    },
                )
        return cleaned

    def titles_for(self, record):
        """One generated title per file, in the order they were submitted."""
        base = DocumentForm._autogenerate_title(
            record,
            self.cleaned_data.get("doc_type"),
            self.cleaned_data.get("issue_date"),
        )
        return [
            f"{base} · {Path(uploaded.name).stem}"[:200]
            for uploaded in self.cleaned_data["files"]
        ]


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
    doc_type = CategorizedDocumentTypeChoiceField(
        queryset=DocumentType.objects.none(), label=_("Document type")
    )
    file = forms.FileField(required=True, label=_("File"))

    class Meta:
        model = Document
        # LV-95: the order the person actually works in -- what this belongs to,
        # what it is, the file, its validity -- and only then the optional
        # fields. `title` used to come first while its own help text says it is
        # derived from the three answers below it, so the form opened by asking
        # for something that could not be answered yet.
        fields = (
            "entity_type",
            "object_id",
            "doc_type",
            "file",
            "issue_date",
            "expiry_date",
            "title",
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
        # LV-79: DocumentCreate proposes the dates the linked record already
        # holds. Say where they came from, or a pre-filled field reads as a
        # value someone else entered and nobody dares correct it -- and the
        # DGAC can perfectly well issue a resolution on a date of its own.
        if not self.is_bound:
            for name in ("issue_date", "expiry_date"):
                if self.initial.get(name):
                    self.fields[name].help_text = _(
                        "Taken from the linked record. Correct it if the "
                        "document says otherwise."
                    )
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
        # The type already on the document survives even if it was archived
        # (DocumentReplace prefills it) -- see selectable_document_types.
        current_type = self.initial.get("doc_type") or getattr(
            self.instance, "doc_type_id", None
        )
        self.fields["doc_type"].queryset = selectable_document_types(
            current_pk=getattr(current_type, "pk", current_type)
        )
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
            for error in upload_errors(uploaded):
                self.add_error("file", error)
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

    def save(self, commit=True):
        document = super().save(commit=False)
        document.content_type = self.cleaned_data["entity_type"]
        if commit:
            document.save()
        return document


class DocumentTypeForm(AeroModelForm):
    class Meta:
        model = DocumentType
        # LV-95: `category` is here, not left to its default -- a type created
        # from this screen without one would land under "Other" and quietly
        # undo the grouping for the next person who looks for it.
        fields = ["name", "code", "category", "requires_expiry", "is_insurance"]
        # LV-22: without explicit labels Django auto-derives an English one
        # ("Requires expiry") whose msgid is in no catalog, so it renders in
        # English inside the Spanish UI.
        labels = {
            "name": _("Name"),
            "code": _("Code"),
            "category": _("Category"),
            "requires_expiry": _("Requires expiry"),
            "is_insurance": _("Is insurance"),
        }


class AlertRuleForm(AeroModelForm):
    """Both fields are pickers, not free text.

    field_to_watch depends on the chosen entity, so its options are narrowed to
    that model once one is selected (on a bound form or when editing); before
    that it offers every watchable field and the model's clean() rejects a
    mismatch.

    **LV-78 step 3a:** `create_kanban_task`, `target_board` and `target_stage`
    left this form. The board was decommissioned and frozen, and the form was
    still the way to *switch on* automatic card creation into it -- a loaded gun
    on a screen somebody edits for unrelated reasons. The columns stay (nothing
    is deleted until the board itself goes); what is removed is the ability to
    turn this on from the UI. A rule that already has it enabled keeps behaving
    exactly as before, and `generate_alerts` now says so out loud instead of
    filing cards into a board nobody opens.
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
        ]
        labels = {
            "name": _("Name"),
            "days_before_expiry": _("Days before expiry"),
            "enabled": _("Enabled"),
        }

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
        labels = {
            "alert_rule": _("Alert rule"),
            "content_type": _("Content type"),
            "object_id": _("Object id"),
            "message": _("Message"),
        }


class DeliverableForm(AeroModelForm):
    """R7.4. `status` is not editable here: it moves through the validate /
    release / reject actions, which carry the signature and the gate. A status
    dropdown would let someone type "released" past the acceptance check."""

    class Meta:
        model = Deliverable
        fields = [
            "title",
            "cost_center",
            "flight_permissions",
            "gsd_achieved_cm",
            "rmse_xy_cm",
            "rmse_z_cm",
            "gcp_count",
            "checkpoint_count",
            "coverage_pct",
            "overlap_pct",
            "notes",
        ]
        widgets = {"flight_permissions": forms.CheckboxSelectMultiple}
        labels = {
            "title": _("Title"),
            "cost_center": _("Cost center"),
            "flight_permissions": _("Flight permissions"),
            "gsd_achieved_cm": _("Achieved GSD (cm)"),
            "rmse_xy_cm": _("Horizontal RMSE (cm)"),
            "rmse_z_cm": _("Vertical RMSE (cm)"),
            "gcp_count": _("Control points"),
            "checkpoint_count": _("Check points"),
            "coverage_pct": _("Coverage (%)"),
            "overlap_pct": _("Overlap (%)"),
            "notes": _("Notes"),
        }
        help_texts = {
            "gsd_achieved_cm": _(
                "Compared against the cost center's required GSD, when set."
            ),
            "checkpoint_count": _(
                "Points held back from the adjustment. An RMSE computed only "
                "over control points is not an independent check."
            ),
        }


class NonConformityForm(AeroModelForm):
    """R7.6. `status` is not a field: closing goes through the action that
    checks the root cause is on record first."""

    class Meta:
        model = NonConformity
        fields = [
            "title",
            "source",
            "cost_center",
            "detected_on",
            "description",
            "root_cause",
            "corrective_action",
            "reported_to_dgac_at",
            "dgac_report_reference",
            "notes",
        ]
        labels = {
            "title": _("Title"),
            "source": _("Source"),
            "cost_center": _("Cost center"),
            "detected_on": _("Detected on"),
            "description": _("Description"),
            "root_cause": _("Root cause"),
            "corrective_action": _("Corrective action"),
            "reported_to_dgac_at": _("Reported to DGAC on"),
            "dgac_report_reference": _("DGAC report reference"),
            "notes": _("Notes"),
        }
        help_texts = {
            "root_cause": _(
                "Required before closing. Leave blank until it is actually "
                "investigated -- a placeholder looks answered."
            ),
            "reported_to_dgac_at": _(
                "Only when the event required notifying the authority."
            ),
        }


class AlertResolveForm(forms.Form):
    """R6.2: ISO 10.2 asks for the root cause on record, not just "handled".
    A plain Form, not a ModelForm -- this only ever feeds Alert.resolve(),
    never a direct model save, and the field it collects (the reason) does
    not have to exist until resolution."""

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        label=_("Reason / root cause"),
        help_text=_("Why this happened and how it was addressed."),
    )
