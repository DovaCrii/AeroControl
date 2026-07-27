from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import FlightPermission, FlightRecord


class FlightPermissionForm(AeroModelForm):
    class Meta:
        model = FlightPermission
        fields = [
            "permission_number",
            "operators",
            "aircraft_fleet",
            "cost_center",
            "purpose",
            "valid_from",
            "valid_until",
            "location",
        ]
        widgets = {
            # A roster of several, not one pick from a dropdown (OPS-4).
            "operators": forms.CheckboxSelectMultiple,
            "aircraft_fleet": forms.CheckboxSelectMultiple,
        }


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
