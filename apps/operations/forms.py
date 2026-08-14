from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import FlightPermission, FlightRecord


class FlightPermissionForm(AeroModelForm):
    class Meta:
        model = FlightPermission
        # LV-39: status first, then the number -- a permit is built while it is
        # still "requested" (or "denied"), before it has a DGAC folio.
        fields = [
            "status",
            "permission_number",
            "operators",
            "aircraft_fleet",
            "cost_center",
            "purpose",
            "purpose_detail",
            "valid_from",
            "valid_until",
            "location",
            "region",
            "commune",
            "area_name",
            "latitude",
            "longitude",
            "radius_km",
            "max_altitude_ft",
            "area_type",
        ]
        # LV-22: without explicit labels the auto-generated English ones ("Permission
        # number", "Valid from"…) fell through the catalog and rendered in English
        # inside the Spanish UI.
        labels = {
            "status": _("Status"),
            "permission_number": _("Permission number"),
            "operators": _("Operators"),
            "aircraft_fleet": _("Aircraft fleet"),
            "cost_center": _("Cost center"),
            "purpose": _("Purpose"),
            "purpose_detail": _("Purpose detail"),
            "valid_from": _("Valid from"),
            "valid_until": _("Valid until"),
            "location": _("Location"),
            "region": _("Region"),
            "commune": _("Commune"),
            "area_name": _("Area or site name"),
            "latitude": _("Latitude"),
            "longitude": _("Longitude"),
            "radius_km": _("Radius (km)"),
            "max_altitude_ft": _("Maximum altitude (ft)"),
            "area_type": _("Area type"),
        }
        help_texts = {
            "permission_number": _("Optional until the permission is approved."),
            "area_type": _("DAN 151 (populated) vs. DAN 91 (unpopulated)."),
            "purpose_detail": _("Required when purpose is 'Other'."),
            "region": _(
                "Structured location, in addition to the free-text location "
                "above -- optional."
            ),
            "latitude": _("Decimal degrees. Enter together with longitude."),
            "longitude": _("Decimal degrees. Enter together with latitude."),
        }
        widgets = {
            # A roster of several, not one pick from a dropdown (OPS-4).
            "operators": forms.CheckboxSelectMultiple,
            "aircraft_fleet": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # LV-39: the folio is only demanded once approved (see clean); until then
        # the permit can be assembled without it.
        self.fields["permission_number"].required = False
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # roster with several of the same model.
        self.fields["aircraft_fleet"].label_from_instance = lambda obj: (
            obj.selector_label
        )

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        number = (cleaned.get("permission_number") or "").strip()
        if status == "approved" and not number:
            self.add_error(
                "permission_number",
                _("An approved permission needs its DGAC number."),
            )
        # Store null (not "") so several folio-less permits don't collide on the
        # unique index.
        cleaned["permission_number"] = number or None
        self.instance.permission_number = cleaned["permission_number"]
        return cleaned


class FlightPermissionUpdateForm(FlightPermissionForm):
    """LV-101: the same form, minus the status.

    Editing a permit used to offer `status` as a free dropdown, which made the
    edit screen a **back door around every guard the status flow has**: it could
    reach "approved" without the signed DGAC authorization that
    `RequireDgacPermitPdfMixin` demands, walk backwards through the flow, and --
    because `FlightPermissionUpdate` never set `_changed_by` -- write the
    resulting history row attributed to `"system"`. Found in production on
    `JEJ-2026-001`: *"Aprobado desde Completado · system"*.

    Creation keeps the field (LV-39's reason still holds: a permit is assembled
    while it is still "requested"). Changing the status of an existing permit
    now has exactly two doors, both of which record who and why: the guarded
    transitions, and `FlightPermissionCorrectStatus` for genuine corrections.
    """

    class Meta(FlightPermissionForm.Meta):
        fields = [
            field for field in FlightPermissionForm.Meta.fields if field != "status"
        ]

    def clean(self):
        # The parent rejects an approved permit with no DGAC folio, reading the
        # status from cleaned_data -- absent here, so it comes from the instance
        # instead. Dropping the field must not drop the rule with it.
        cleaned = super().clean()
        cleaned["status"] = self.instance.status
        number = (cleaned.get("permission_number") or "").strip()
        if self.instance.status == "approved" and not number:
            self.add_error(
                "permission_number",
                _("An approved permission needs its DGAC number."),
            )
        return cleaned


class StatusCorrectionForm(forms.Form):
    """LV-101: fixing a status that is simply wrong, on the record.

    Corrections are real -- the defect above was found *because* somebody used
    the edit screen to undo a mistaken "completed". Removing the back door
    without offering a front door would only push the same act into `/admin/`,
    where it would still be unattributed. So the correction exists, but it costs
    a written reason: the same trade `AlertResolveForm` makes for ISO 10.2, and
    the difference between an audit trail that explains itself and one that says
    "system".
    """

    status = forms.ChoiceField(choices=(), label=_("Corrected status"))
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Reason for the correction"),
        help_text=_(
            "Why the recorded status was wrong. It stays in the permit's "
            "history, so write it for whoever reads this a year from now."
        ),
    )

    def __init__(self, *args, current_status=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Every status except the one it already has: "correcting" a permit to
        # the status it is already in is not a correction, and would write a
        # history row saying nothing happened.
        self.fields["status"].choices = [
            (value, label)
            for value, label in FlightPermission.STATUS_CHOICES
            if value != current_status
        ]

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise ValidationError(_("Write why the status is being corrected."))
        return reason


class FlightRecordForm(AeroModelForm):
    class Meta:
        model = FlightRecord
        fields = [
            "permission",
            "actual_date",
            "departure_time",
            "arrival_time",
            "pilot",
            "aircraft",
        ]
        labels = {
            "permission": _("Flight permission"),
            "actual_date": _("Flight date"),
            "departure_time": _("Departure time"),
            "arrival_time": _("Arrival time"),
            "pilot": _("Pilot"),
            "aircraft": _("Aircraft"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # LV-59: the "permission" field had no queryset override, so it fell
        # back to the ModelForm default (every FlightPermission ever created,
        # in raw pk order) -- unusable once there are more than a handful.
        # This is the picker someone actually sees when creating a flight
        # record from the standalone Vuelos list rather than from a specific
        # permission's own "+ Agregar registro" (which prefills it and never
        # shows this dropdown); the T5.5 narrowing below only starts once a
        # permission is already chosen, so it does not help here.
        self.fields["permission"].queryset = FlightPermission.objects.filter(
            is_active=True
        ).order_by("-valid_from")
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # dropdown with several of the same model.
        self.fields["aircraft"].label_from_instance = lambda obj: obj.selector_label
        # T5.5: once a permission is chosen (prefilled from its detail page, or
        # posted back), narrow the pilot and aircraft pickers to that
        # permission's roster instead of the whole registry. The clean() below
        # still enforces it, but this stops the user picking an invalid option
        # in the first place -- the form reduces to what the permission allows.
        permission_id = (
            self.data.get("permission")
            or self.initial.get("permission")
            or getattr(self.instance, "permission_id", None)
        )
        if not permission_id:
            return
        try:
            permission = FlightPermission.objects.prefetch_related(
                "operators", "aircraft_fleet"
            ).get(pk=permission_id)
        except (FlightPermission.DoesNotExist, ValidationError, ValueError, TypeError):
            return
        self.fields["pilot"].queryset = permission.operators.filter(is_active=True)
        self.fields["aircraft"].queryset = permission.aircraft_fleet.filter(
            is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        permission = cleaned.get("permission")
        pilot = cleaned.get("pilot")
        aircraft = cleaned.get("aircraft")
        actual_date = cleaned.get("actual_date")
        departure = cleaned.get("departure_time")
        arrival = cleaned.get("arrival_time")
        # OPS-4: the permission now lists a roster of operators/aircraft over a
        # date range, not a single one of each on a single day, so a flight
        # record is valid whenever it falls within that roster and range --
        # not an exact match against "the" operator/aircraft/date.
        if (
            permission
            and aircraft
            and not permission.aircraft_fleet.filter(pk=aircraft.pk).exists()
        ):
            self.add_error(
                "aircraft",
                _("The aircraft must be part of the flight permission's fleet."),
            )
        if (
            permission
            and pilot
            and not permission.operators.filter(pk=pilot.pk).exists()
        ):
            self.add_error(
                "pilot",
                _("The pilot must be one of the flight permission's operators."),
            )
        if (
            permission
            and actual_date
            and not (permission.valid_from <= actual_date <= permission.valid_until)
        ):
            self.add_error(
                "actual_date",
                _(
                    "The flight date must fall within the flight permission's validity range."
                ),
            )
        if departure and arrival and arrival <= departure:
            self.add_error(
                "arrival_time", _("Arrival time must be later than departure time.")
            )
        return cleaned
