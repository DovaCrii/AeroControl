from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import (
    Aircraft,
    AircraftAssignment,
    Assignment,
    CostCenter,
    Operator,
    OperatorAssignment,
    Qualification,
    QualificationType,
)


class CostCenterForm(AeroModelForm):
    class Meta:
        model = CostCenter
        # LV-16 dropped "Nombre" from the form; LV-19 brought it back as an
        # *optional* field: names shown in the list (e.g. "Casa Matriz",
        # "Levantamientos digital") were otherwise frozen -- there was no way to
        # set or fix a cost center's name without the Django admin.
        fields = [
            "code",
            "name",
            "responsible",
            "responsible_operator",
            "responsible_contact_name",
            "responsible_contact_email",
            "notes",
        ]
        labels = {
            "code": _("Code"),
            "name": _("Name"),
            "responsible": _("Contract administrator name"),
            "responsible_operator": _("Responsible operator"),
            "responsible_contact_name": _("External contact name"),
            "responsible_contact_email": _("External contact email"),
            "notes": _("Notes"),
        }
        help_texts = {
            "name": _("Optional descriptive name (e.g. Casa Matriz)."),
            "responsible_operator": _(
                "Recipient of expiry digests. Use when the responsible person "
                "is in the operator roster."
            ),
            "responsible_contact_name": _(
                "Use instead of the operator when the responsible person is "
                "external to the system (an administrator, secretary, or "
                "safety officer). Also used for the digest if the operator "
                "above has no reachable email."
            ),
            # LV-10a: the "CC" prefix is fixed, not typed. Enforced in
            # clean_code so the stored value is always CC<number>.
            "code": _("Enter the number only; the CC prefix is added automatically."),
        }

    def clean_code(self):
        """LV-10a: every cost-center code carries a fixed 'CC' prefix.

        Whatever the user types (with or without a leading CC) is normalised to
        uppercase 'CC' + the remainder, so the stored code is the single source
        of truth everywhere (list, __str__, exports, search). The 11 legacy
        codes were prefixed by a data migration.
        """
        raw = (self.cleaned_data.get("code") or "").strip().upper()
        remainder = raw[2:] if raw.startswith("CC") else raw
        remainder = remainder.strip()
        if not remainder:
            raise forms.ValidationError(_("Enter the cost-center number."))
        return f"CC{remainder}"


class AircraftForm(AeroModelForm):
    class Meta:
        model = Aircraft
        fields = [
            "registration",
            "type",
            "model",
            "manufacturer",
            "year",
            "serial_number",
            "max_takeoff_weight_kg",
            "basic_weight_kg",
            "vlos",
            "parachute",
            "insurance_expiry",
            "authorized_services",
            "cost_center",
            "status",
            "current_location",
            "current_site",
        ]
        labels = {
            "registration": _("Registration"),
            "type": _("Type"),
            "model": _("Model"),
            "manufacturer": _("Manufacturer"),
            "year": _("Year"),
            "serial_number": _("Serial number"),
            "max_takeoff_weight_kg": _("Maximum takeoff weight (kg)"),
            "basic_weight_kg": _("Basic weight (kg)"),
            "vlos": _("VLOS"),
            "parachute": _("Parachute"),
            "insurance_expiry": _("JAC insurance expiry"),
            "authorized_services": _("Authorized services"),
            "cost_center": _("Cost Center"),
            "status": _("Status"),
            "current_location": _("Current location"),
            "current_site": _("Current site"),
        }

    # LV-25: VLOS and parachute were free text that drifted; offer the values
    # actually in use as a dropdown instead. The options are built in __init__
    # from the column itself plus a small default set, and the row's own stored
    # value is always included -- so turning the field into a ChoiceField never
    # rejects a legacy value on edit (soft normalization, no data migration).
    VLOS_DEFAULTS = ("VLOS", "BVLOS")
    PARACHUTE_DEFAULTS = ("SI", "NO")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._make_choice_field("vlos", self.VLOS_DEFAULTS, _("VLOS"))
        self._make_choice_field("parachute", self.PARACHUTE_DEFAULTS, _("Parachute"))

    def _make_choice_field(self, name, defaults, label):
        values = set(defaults)
        for raw in Aircraft.objects.exclude(**{name: ""}).values_list(name, flat=True):
            if raw and raw.strip():
                values.add(raw.strip())
        current = getattr(self.instance, name, "") or ""
        if current:
            values.add(current)
        choices = [("", "—")] + [(value, value) for value in sorted(values)]
        self.fields[name] = forms.ChoiceField(
            choices=choices, required=False, label=label
        )

    def clean(self):
        # LV-20: a "site" only means something when the aircraft is on site.
        # The model guards this too, but on the form the raised error made
        # Save look broken (the 422 re-rendered without surfacing it): the user
        # picks Headquarters/Maintenance and the still-selected site blocks the
        # save. Clear it silently instead -- the location field is what they set.
        cleaned = super().clean()
        if cleaned.get("current_location") != "on_site":
            cleaned["current_site"] = None
        return cleaned


class OperatorForm(AeroModelForm):
    class Meta:
        model = Operator
        fields = [
            "employee_id",
            "full_name",
            "email",
            "phone",
            "rut",
            "dgac_credential",
            "credential_expiry",
            "operator_type",
            "address",
            "authorizations",
            "cost_center",
        ]
        labels = {
            "employee_id": _("Employee ID"),
            "full_name": _("Full name"),
            "email": _("Email"),
            "phone": _("Phone"),
            "rut": _("RUT"),
            "dgac_credential": _("DGAC credential"),
            "credential_expiry": _("DGAC credential expiry"),
            "operator_type": _("Operator type"),
            "address": _("Address"),
            "authorizations": _("Authorizations"),
            "cost_center": _("Cost Center"),
        }


class AssignmentForm(AeroModelForm):
    class Meta:
        model = Assignment
        fields = [
            "operator",
            "aircraft",
            "cost_center",
            "purpose",
            "start_date",
            "end_date",
            "status",
        ]
        labels = {
            "operator": _("Operator"),
            "aircraft": _("Aircraft"),
            "cost_center": _("Cost center"),
            "purpose": _("Operation or purpose"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
        }

    # A previous __init__ here re-translated Assignment.STATUS_CHOICES at
    # runtime. That is no longer needed: the choices carry gettext_lazy labels
    # in the model, so the form picks up the active language on its own.
    # Verified identical output both ways before removing it.

    def clean(self):
        cleaned = super().clean()
        operator = cleaned.get("operator")
        aircraft = cleaned.get("aircraft")
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        status = cleaned.get("status")
        cost_center = cleaned.get("cost_center")
        if not operator or not aircraft or not start_date:
            return cleaned
        if status == "confirmed" and not cost_center:
            self.add_error(
                "cost_center",
                _("A confirmed assignment requires a cost center."),
            )
        end = end_date or start_date
        overlap = Assignment.objects.filter(
            is_active=True,
            operator=operator,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        overlap = overlap.filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if status == "confirmed" and overlap.filter(status="confirmed").exists():
            self.add_error(
                "operator",
                _("This operator already has a confirmed assignment in this period."),
            )

        aircraft_overlap = Assignment.objects.filter(
            is_active=True,
            aircraft=aircraft,
            start_date__lte=end,
        ).exclude(pk=self.instance.pk)
        aircraft_overlap = aircraft_overlap.filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if (
            status == "confirmed"
            and aircraft_overlap.filter(status="confirmed").exists()
        ):
            self.add_error(
                "aircraft",
                _("This aircraft already has a confirmed assignment in this period."),
            )
        return cleaned


class OperatorAssignmentForm(AeroModelForm):
    """OPS-1 per-resource assignment: an operator anchored to a cost center.

    LV-17: the dates are not what the user tracks here -- the cost center and
    the status are. `start_date` (required on the model) is filled in with today
    on create, so it stays off the form. Editing an existing row keeps its date.

    No custom clean() needed: ModelForm._post_clean() calls instance.full_clean(),
    which runs ResourceAssignment.clean() (the overlap check) and attaches its
    errors to the right field.
    """

    class Meta:
        model = OperatorAssignment
        fields = [
            "operator",
            "cost_center",
            "status",
            "purpose",
        ]
        labels = {
            "operator": _("Operator"),
            "cost_center": _("Cost center"),
            "status": _("Status"),
            "purpose": _("Operation or purpose"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # start_date stays required on the model but off the form (LV-17). Set it
        # here, before validation runs: the overlap check reads start_date, so a
        # None left until save() would break _overlapping's date filter.
        if self.instance.start_date is None:
            from django.utils import timezone

            self.instance.start_date = timezone.localdate()


class OperatorBulkAssignForm(forms.Form):
    """LV-18: assign several operators to one cost center at once.

    Only the cost center, the operators and the status matter (no dates, per
    LV-17). Reassigning an operator already placed elsewhere moves them; see
    apps.registry.services.bulk_assign_operators.
    """

    cost_center = forms.ModelChoiceField(
        queryset=CostCenter.objects.filter(is_active=True).order_by("code"),
        label=_("Cost center"),
    )
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.filter(is_active=True).order_by("full_name"),
        label=_("Operators"),
        widget=forms.SelectMultiple(attrs={"size": 12}),
        help_text=_(
            "Select one or more. Each is assigned to the cost center above; "
            "an operator already assigned elsewhere is moved here."
        ),
    )
    status = forms.ChoiceField(
        choices=OperatorAssignment.STATUS_CHOICES,
        initial="active",
        label=_("Status"),
    )
    purpose = forms.CharField(
        max_length=250,
        required=False,
        label=_("Operation or purpose"),
    )


class AircraftAssignmentForm(AeroModelForm):
    """OPS-1 per-resource assignment: an aircraft anchored to a cost center."""

    class Meta:
        model = AircraftAssignment
        fields = [
            "aircraft",
            "cost_center",
            "start_date",
            "end_date",
            "status",
            "purpose",
        ]
        labels = {
            "aircraft": _("Aircraft"),
            "cost_center": _("Cost center"),
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "status": _("Status"),
            "purpose": _("Operation or purpose"),
        }


class QualificationForm(AeroModelForm):
    class Meta:
        model = Qualification
        fields = ["operator", "qualification_type", "issue_date", "expiry_date"]
        labels = {
            "operator": _("Operator"),
            "qualification_type": _("Qualification type"),
            "issue_date": _("Issue date"),
            "expiry_date": _("Expiry date"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # B4.3/LV-1 parity: an empty catalog makes the required picker look
        # broken. Point at where to create the first type.
        if not QualificationType.objects.filter(is_active=True).exists():
            self.fields["qualification_type"].help_text = _(
                "No qualification types configured yet. Create one first."
            )


class QualificationTypeForm(AeroModelForm):
    class Meta:
        model = QualificationType
        fields = ["name", "code", "model_keywords"]
