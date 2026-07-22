from django import forms

from .models import FlightPermission, FlightRecord


class FlightPermissionForm(forms.ModelForm):
    class Meta:
        model = FlightPermission
        fields = [
            "permission_number",
            "operator",
            "aircraft",
            "cost_center",
            "purpose",
            "flight_date",
            "location",
        ]


class FlightRecordForm(forms.ModelForm):
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
        if permission and aircraft and permission.aircraft_id != aircraft.id:
            self.add_error("aircraft", "The aircraft must match the flight permission.")
        if permission and pilot and permission.operator_id != pilot.id:
            self.add_error(
                "pilot", "The pilot must match the flight permission operator."
            )
        if permission and actual_date and actual_date != permission.flight_date:
            self.add_error(
                "actual_date", "The flight date must match the flight permission."
            )
        if departure and arrival and arrival <= departure:
            self.add_error(
                "arrival_time", "Arrival time must be later than departure time."
            )
        return cleaned
