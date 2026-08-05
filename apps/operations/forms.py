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
            "valid_from",
            "valid_until",
            "location",
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
            "valid_from": _("Valid from"),
            "valid_until": _("Valid until"),
            "location": _("Location"),
        }
        help_texts = {
            "permission_number": _("Optional until the permission is approved."),
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
