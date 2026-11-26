import copy

from django import forms
from django.db.models import Case, IntegerField, Value, When
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.core.forms import AeroModelForm
from apps.core.tenancy import scope_form_choices, scope_queryset_to_tenant
from apps.registry.models import Aircraft, CostCenter, normalize_serial
from .models import (
    AircraftLogbook,
    MaintenanceHistory,
    MaintenanceRecord,
    WorkshopIntake,
    normalize_workshop_name,
    normalize_workshop_order,
)


class MaintenanceRecordForm(AeroModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = [
            "aircraft",
            "maintenance_type",
            "description",
            "scheduled_date",
            "performed_by",
            "level",
        ]
        labels = {
            "level": _("Level"),
            # "Maintenance type" rendered untranslated (LV-8d): the derived
            # label was not in the catalog. Spelled out here so all labels are
            # controlled and translated.
            "aircraft": _("Aircraft"),
            "maintenance_type": _("Maintenance type"),
            "description": _("Description"),
            "scheduled_date": _("Scheduled date"),
            "performed_by": _("Performed by"),
        }
        help_texts = {
            "scheduled_date": _(
                "Leave blank for a 'to be defined' maintenance until it is planned."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # dropdown with several of the same model.
        self.fields["aircraft"].label_from_instance = lambda obj: obj.selector_label


class AircraftLogbookForm(AeroModelForm):
    """LV-443: the baseline of an aircraft's accumulated hours (REG-020)."""

    class Meta:
        model = AircraftLogbook
        fields = ["hours_baseline", "baseline_on"]
        labels = {
            "hours_baseline": _("Hours at baseline date"),
            "baseline_on": _("Baseline date"),
        }
        help_texts = {
            "hours_baseline": _(
                "Total flight hours on the baseline date, from the last "
                "maintenance certificate. Later flights are added to it."
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("hours_baseline") and not cleaned.get("baseline_on"):
            self.add_error(
                "baseline_on",
                _("Enter the date the baseline hours were read."),
            )
        return cleaned


class MaintenanceHistoryForm(AeroModelForm):
    class Meta:
        model = MaintenanceHistory
        fields = ["record", "previous_status", "new_status", "changed_by"]
        # Same reason as MaintenanceRecordForm above: an unlisted field renders
        # Django's derived English label, which is in no catalog.
        labels = {
            "record": _("Record"),
            "previous_status": _("Previous status"),
            "new_status": _("New status"),
            "changed_by": _("Changed by"),
        }


class MaintenanceCompletionForm(AeroModelForm):
    class Meta:
        model = MaintenanceRecord
        # LV-443: the level, the aircraft hours and the certificate number come
        # from the maintenance certificate, so they are captured when closing.
        fields = [
            "completed_date",
            "performed_by",
            "level",
            "hours_at",
            "certificate_number",
            "notes",
        ]
        labels = {
            "level": _("Level"),
            "hours_at": _("Aircraft hours"),
            "certificate_number": _("Certificate number"),
        }
        help_texts = {
            "hours_at": _(
                "Total flight hours of the aircraft when the maintenance was done."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # performed_by is optional on the model (a "to be defined" record has
        # none yet, LV-8b) but completing a maintenance must record who did it
        # and when, so both are required in this context.
        self.fields["completed_date"].required = True
        self.fields["performed_by"].required = True


class MaintenanceCertificateForm(AeroModelForm):
    """LV-460: review and confirm what was read from a maintenance certificate.

    A `ModelForm` only for its labels, widgets and field validation: it is never
    saved. The rule that closes or creates the record is
    `MaintenanceRecord.register_certificate`; this form only collects its data.
    """

    aircraft = forms.ModelChoiceField(
        queryset=Aircraft.objects.none(),
        label=pgettext_lazy("workshop intake", "Aircraft"),
        help_text=_(
            "The serial is matched exactly. If none matches, choose the aircraft "
            "yourself."
        ),
    )
    serial_mismatch_confirmed = forms.BooleanField(
        required=False,
        label=_("Register it on this aircraft even though the serial is different"),
    )

    class Meta:
        model = MaintenanceRecord
        fields = [
            "aircraft",
            "completed_date",
            "certificate_number",
            "performed_by",
            "hours_at",
            "maintenance_type",
            "level",
            "notes",
        ]
        labels = {
            "completed_date": _("Issue date"),
            "certificate_number": _("Certificate number"),
            "performed_by": _("Performed by"),
            "hours_at": _("Aircraft hours"),
            "maintenance_type": _("Maintenance type"),
            "level": _("Level"),
            "notes": _("Notes"),
        }
        help_texts = {
            "completed_date": _(
                "The date the certificate was issued; it becomes the completion "
                "date of the maintenance."
            ),
            "certificate_number": _("The workshop's number for the job."),
            "hours_at": _(
                "Total flight hours of the aircraft when the maintenance was done."
            ),
            "maintenance_type": _(
                "Only used when no open maintenance is found and a new one is recorded."
            ),
            "level": _(
                "The level of the maintenance programme this work completes. Leave "
                "it empty if it is not a programme level."
            ),
        }

    def __init__(self, *args, user, serial="", initial_aircraft=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.read_serial = normalize_serial(serial)
        for name in ("completed_date", "certificate_number", "performed_by"):
            self.fields[name].required = True
        self.fields["maintenance_type"].choices = [
            choice for choice in MaintenanceRecord.TYPES if choice[0] != "to_be_defined"
        ]
        queryset = scope_queryset_to_tenant(
            Aircraft.objects.filter(is_active=True), user
        ).order_by("registration")
        field = self.fields["aircraft"]
        field.queryset = queryset
        field.label_from_instance = lambda obj: obj.selector_label
        if initial_aircraft is not None and not self.is_bound:
            self.initial["aircraft"] = initial_aircraft.pk

    def serial_mismatch(self, aircraft):
        """True when a serial was read and `aircraft` does not carry it."""
        return bool(
            self.read_serial
            and aircraft is not None
            and aircraft.serial_number != self.read_serial
        )

    def clean(self):
        cleaned = super().clean()
        aircraft = cleaned.get("aircraft")
        if self.serial_mismatch(aircraft) and not cleaned.get(
            "serial_mismatch_confirmed"
        ):
            self.add_error(
                "serial_mismatch_confirmed",
                _(
                    "The serial on the document (%(serial)s) is not this aircraft's "
                    "(%(aircraft_serial)s). Check the aircraft, or confirm that the "
                    "certificate belongs to it."
                )
                % {
                    "serial": self.read_serial,
                    "aircraft_serial": aircraft.serial_number or "—",
                },
            )
        return cleaned

    def certificate_data(self, workshop_name=""):
        """The data for `MaintenanceRecord.register_certificate`."""
        data = {
            name: self.cleaned_data.get(name)
            for name in self.Meta.fields
            if name != "aircraft"
        }
        data["workshop_name"] = workshop_name or data.get("performed_by") or ""
        return data


# LV-383 (PR 3): the screen that registers a workshop intake from the workshop's PDF.
# Fields the readers fill from the document, and the quote ones (shown read-only).
INTAKE_READ_FIELDS = (
    "workshop_name",
    "workshop_order",
    "received_at",
    "delivered_by",
    "accessories",
    "findings",
)
INTAKE_QUOTE_FIELDS = (
    "quote_date",
    "quote_valid_until",
    "quote_net",
    "quote_vat",
    "quote_total",
    "quote_lead_time",
    "quote_warranty",
    "diagnosis",
)


def intake_initial(proposal):
    """The values a reader found, as form initial data (empty ones are left out)."""
    if proposal is None:
        return {}
    initial = {}
    for name in (*INTAKE_READ_FIELDS, *INTAKE_QUOTE_FIELDS):
        value = getattr(proposal, name, None)
        if value not in (None, ""):
            initial[name] = value
    return initial


def find_existing_intake(user, workshop_name, workshop_order):
    """The active intake of this (workshop, order) that `user` may see, or `None`.

    A plain read (no row lock): it only decides what the screen says. The rule that
    completes the intake is `MaintenanceRecord.register_workshop_intake`. Scoped to
    the user's company so the screen never links another company's record.
    """
    order = normalize_workshop_order(workshop_order)
    if not order or not (workshop_name or "").strip():
        return None
    queryset = WorkshopIntake.objects.filter(
        workshop_key=normalize_workshop_name(workshop_name),
        workshop_order=order,
        is_active=True,
    ).select_related("record")
    return scope_queryset_to_tenant(
        queryset, user, "record__aircraft__tenant_id"
    ).first()


class WorkshopIntakeForm(AeroModelForm):
    """Review and confirm what was read from a workshop document.

    Nothing from the document travels through the client except what the person
    edits: the quote fields are `disabled`, so Django ignores whatever is posted
    for them and takes the value the server read from the stored file.
    """

    aircraft = forms.ModelChoiceField(
        queryset=Aircraft.objects.none(),
        label=pgettext_lazy("workshop intake", "Aircraft"),
        help_text=_(
            "The serial is matched exactly. If none matches, choose the aircraft "
            "yourself."
        ),
    )
    # Required with an empty first option: the person must pick, never inherit it.
    sent_by = forms.ChoiceField(
        choices=[("", _("Select…")), *WorkshopIntake.SENT_BY_CHOICES],
        label=_("Sent by"),
        help_text=_("Confirm who sent the equipment to the workshop."),
    )

    class Meta:
        model = WorkshopIntake
        fields = [
            "workshop_name",
            "workshop_order",
            "received_at",
            "sent_by",
            "sender_cost_center",
            "delivered_by",
            "accessories",
            "findings",
            *INTAKE_QUOTE_FIELDS,
        ]
        labels = {
            "workshop_name": _("Workshop"),
            "workshop_order": _("Workshop order"),
            "received_at": _("Received at"),
            "sender_cost_center": _("Sending cost center"),
            "delivered_by": _("Delivered by"),
            "accessories": _("Accessories"),
            "findings": _("Findings"),
            "quote_date": _("Quote date"),
            "quote_valid_until": _("Quote valid until"),
            "quote_net": _("Quote net amount"),
            "quote_vat": _("Quote VAT"),
            "quote_total": _("Quote total"),
            "quote_lead_time": _("Quote lead time"),
            "quote_warranty": _("Quote warranty"),
            "diagnosis": _("Diagnosis"),
        }
        help_texts = {
            "received_at": _("Leave blank if the document has no reception date."),
        }

    def __init__(
        self,
        *args,
        user,
        proposal=None,
        aircraft_matches=(),
        preselected=None,
        **kwargs,
    ):
        read = intake_initial(proposal)
        # `sent_by` starts empty: the person must pick it, never inherit a default.
        kwargs["initial"] = {"sent_by": "", **read, **kwargs.get("initial", {})}
        super().__init__(*args, **kwargs)
        self.user = user
        self.proposal = proposal
        self.has_quote = any(name in read for name in INTAKE_QUOTE_FIELDS)

        # The order may already be registered (the quote came first, or the other way
        # round): then the form completes that intake instead of colliding with it.
        name = (
            self.data.get(self.add_prefix("workshop_name"))
            if self.is_bound
            else self.initial.get("workshop_name")
        )
        order = (
            self.data.get(self.add_prefix("workshop_order"))
            if self.is_bound
            else self.initial.get("workshop_order")
        )
        self.existing = find_existing_intake(user, name, order)
        if self.is_bound and self.existing is not None:
            # A copy: the model's own `clean()` excludes this pk from its duplicate
            # check, and the in-memory values the form writes are never saved.
            self.instance = copy.copy(self.existing)

        self._setup_aircraft(aircraft_matches, preselected)
        self.fields["sender_cost_center"].queryset = CostCenter.objects.filter(
            is_active=True
        )
        self.fields["sender_cost_center"].required = False
        scope_form_choices(self, user)

        if self.has_quote:
            for field_name in INTAKE_QUOTE_FIELDS:
                self.fields[field_name].disabled = True
        else:
            for field_name in INTAKE_QUOTE_FIELDS:
                del self.fields[field_name]

    def _setup_aircraft(self, matches, preselected):
        queryset = Aircraft.objects.filter(is_active=True)
        if len(matches) > 1:
            queryset = queryset.filter(pk__in=[a.pk for a in matches])
        label = (getattr(self.proposal, "equipment_label", "") or "").casefold()
        same_model = []
        if label:
            same_model = [
                pk
                for pk, model in queryset.values_list("pk", "model")
                if model and (model.casefold() in label or label in model.casefold())
            ]
        field = self.fields["aircraft"]
        if same_model:
            queryset = queryset.annotate(
                same_model=Case(
                    When(pk__in=same_model, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("same_model", "registration")
        else:
            queryset = queryset.order_by("registration")
        field.queryset = queryset
        field.label_from_instance = lambda obj: obj.selector_label

        chosen = matches[0] if len(matches) == 1 else preselected
        if chosen is not None and not self.is_bound:
            self.initial["aircraft"] = chosen.pk
            if chosen.cost_center_id:
                # Pre-selected, not decided: the field stays required and visible.
                self.initial["sent_by"] = "cost_center"
                self.initial["sender_cost_center"] = chosen.cost_center_id

    def register_data(self):
        """The `WorkshopIntake` fields for `register_workshop_intake` (no aircraft)."""
        data = dict(self.cleaned_data)
        data.pop("aircraft", None)
        return data
