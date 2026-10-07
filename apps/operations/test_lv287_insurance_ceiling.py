"""LV-287: un permiso solicitado no puede correr más allá del seguro de sus aeronaves.

Pedido del usuario (2026-10-07), con la captura de una solicitud del portal de SIGO
(operación del 13/10 al 20/12/2026, seguro JAC hasta el 21/12/2026): el techo de tres
meses cede ante el seguro, y la fecha recomendada es **la víspera** del vencimiento.
Si el seguro vence el 21 de diciembre, el permiso llega hasta el 20.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.operations.forms import FlightPermissionForm
from apps.operations.models import FlightPermission
from apps.operations.permit_rules import insurance_cutoff, insurance_window_errors
from apps.registry.models import Aircraft, CostCenter, Operator

START = date(2026, 10, 13)
EXPIRY = date(2026, 12, 21)  # el de la captura


def _aircraft(registration, expiry):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3E",
        manufacturer="DJI",
        insurance_expiry=expiry,
    )


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(
        code="CC861", name="Talabre", operates_flights=True
    )


@pytest.fixture
def operator(centre):
    return Operator.objects.create(
        employee_id="E287", full_name="Piloto Uno", cost_center=centre
    )


def _form(centre, operator, aircraft, *, start=START, end, status="requested", **extra):
    data = {
        "status": status,
        "purpose": "photogrammetry",
        "location": "Sector",
        "area_type": "unpopulated",
        "cost_center": str(centre.pk),
        "operators": [str(operator.pk)],
        "aircraft_fleet": [str(item.pk) for item in aircraft],
        "valid_from": start.isoformat() if start else "",
        "valid_until": end.isoformat() if end else "",
    }
    data.update(extra)
    return FlightPermissionForm(data=data)


class TestThePureRule:
    class _Plane:
        def __init__(self, registration, expiry):
            self.registration = registration
            self.insurance_expiry = expiry

    def test_the_cutoff_is_the_day_before_the_expiry(self):
        limit, plane = insurance_cutoff([self._Plane("RPA-1", EXPIRY)])

        assert limit == date(2026, 12, 20)
        assert plane.registration == "RPA-1"

    def test_the_earliest_expiry_among_several_aircraft_governs(self):
        planes = [
            self._Plane("LATE", date(2027, 6, 1)),
            self._Plane("SOON", date(2026, 11, 10)),
        ]

        limit, plane = insurance_cutoff(planes)

        assert limit == date(2026, 11, 9)
        assert plane.registration == "SOON"

    def test_an_aircraft_without_a_date_restricts_nothing(self):
        """No haber cargado la fecha es «desconocido», no «vencido» (LV-29)."""
        assert insurance_cutoff([self._Plane("RPA-1", None)]) is None
        assert insurance_window_errors(START, date(2027, 5, 1), []) == {}

    def test_an_undated_aircraft_does_not_hide_a_dated_one(self):
        planes = [self._Plane("NONE", None), self._Plane("DATED", EXPIRY)]

        assert insurance_cutoff(planes)[0] == date(2026, 12, 20)


@pytest.mark.django_db
class TestTheForm:
    def test_the_day_before_the_expiry_is_accepted(self, centre, operator):
        plane = _aircraft("RPA-3696", EXPIRY)

        form = _form(centre, operator, [plane], end=date(2026, 12, 20))

        assert form.is_valid(), form.errors

    def test_the_expiry_day_itself_is_refused_and_the_eve_is_recommended(
        self, centre, operator
    ):
        plane = _aircraft("RPA-3696", EXPIRY)

        form = _form(centre, operator, [plane], end=EXPIRY)

        assert not form.is_valid()
        message = " ".join(form.errors["valid_until"])
        assert "RPA-3696" in message
        assert "2026-12-21" in message  # cuándo vence el seguro
        assert "2026-12-20" in message  # la fecha que se recomienda

    def test_a_later_date_is_refused_too(self, centre, operator):
        plane = _aircraft("RPA-3696", EXPIRY)

        form = _form(centre, operator, [plane], end=date(2026, 12, 22))

        assert "valid_until" in form.errors

    def test_with_the_insurance_far_away_the_three_months_still_govern(
        self, centre, operator
    ):
        """«Cuando tiene seguro vigente puede optar hasta los 3 meses.»"""
        plane = _aircraft("RPA-1", date(2027, 12, 31))

        inside = _form(centre, operator, [plane], end=date(2027, 1, 13))
        beyond = _form(centre, operator, [plane], end=date(2027, 1, 14))

        assert inside.is_valid(), inside.errors
        assert "valid_until" in beyond.errors

    def test_the_earliest_insurance_among_the_chosen_aircraft_decides(
        self, centre, operator
    ):
        late = _aircraft("RPA-LATE", date(2027, 6, 1))
        soon = _aircraft("RPA-SOON", date(2026, 11, 10))

        form = _form(centre, operator, [late, soon], end=date(2026, 12, 1))

        assert "valid_until" in form.errors
        assert "RPA-SOON" in " ".join(form.errors["valid_until"])

    def test_an_insurance_already_out_by_the_start_is_a_start_date_problem(
        self, centre, operator
    ):
        """Ninguna fecha de término lo arregla: hay que renovar el seguro."""
        plane = _aircraft("RPA-OLD", date(2026, 10, 1))

        form = _form(centre, operator, [plane], end=date(2026, 10, 20))

        assert "valid_from" in form.errors
        assert "valid_until" not in form.errors

    def test_the_override_reason_does_not_skip_the_insurance(self, centre, operator):
        """Ese motivo es para un plazo que la DGAC concedió distinto; el seguro no es
        un plazo de la DGAC."""
        plane = _aircraft("RPA-3696", EXPIRY)

        form = _form(
            centre,
            operator,
            [plane],
            end=EXPIRY,
            validity_override_reason="Resolución DGAC 1234",
        )

        assert "valid_until" in form.errors

    def test_an_aircraft_with_no_insurance_date_restricts_nothing(
        self, centre, operator
    ):
        plane = _aircraft("RPA-NODATE", None)

        form = _form(centre, operator, [plane], end=date(2027, 1, 13))

        assert form.is_valid(), form.errors

    def test_changing_the_fleet_in_the_form_judges_the_new_fleet_not_the_old(
        self, centre, operator
    ):
        """Un M2M no se lee antes de guardar, y la base tiene la flota **vieja**: si el
        modelo la juzgara, rechazaría justo la corrección."""
        old = _aircraft("RPA-OLD", date(2026, 11, 1))
        new = _aircraft("RPA-NEW", date(2027, 6, 1))
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="requested",
            location="Sector",
            area_type="unpopulated",
            valid_from=date(2026, 10, 13),
            valid_until=date(2026, 10, 30),
        )
        permit.aircraft_fleet.add(old)
        permit.operators.add(operator)

        form = FlightPermissionForm(
            instance=permit,
            data={
                "status": "requested",
                "purpose": "photogrammetry",
                "location": "Sector",
                "area_type": "unpopulated",
                "cost_center": str(centre.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(new.pk)],  # cambia la flota
                "valid_from": "2026-10-13",
                "valid_until": "2026-12-01",  # pasa del seguro de la vieja
            },
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestApprovedPermitsAreNotRestricted:
    """Un permiso aprobado refleja lo que la DGAC ya emitió."""

    def test_an_approved_window_past_the_insurance_is_left_alone(
        self, centre, operator
    ):
        plane = _aircraft("RPA-3696", EXPIRY)
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="approved",
            permission_number="6551",
            location="Sector",
            area_type="unpopulated",
            valid_from=START,
            valid_until=date(2026, 12, 21),
        )
        permit.aircraft_fleet.add(plane)

        permit.clean()  # no lanza


@pytest.mark.django_db
class TestTheModelMirrorsIt:
    def _requested(self, centre, end):
        return FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="requested",
            location="Sector",
            area_type="unpopulated",
            valid_from=START,
            valid_until=end,
        )

    def test_a_saved_request_past_the_insurance_fails_its_clean(self, centre):
        permit = self._requested(centre, EXPIRY)
        permit.aircraft_fleet.add(_aircraft("RPA-3696", EXPIRY))

        with pytest.raises(ValidationError) as error:
            permit.clean()

        assert "valid_until" in error.value.error_dict

    def test_a_saved_request_on_the_eve_passes(self, centre):
        permit = self._requested(centre, date(2026, 12, 20))
        permit.aircraft_fleet.add(_aircraft("RPA-3696", EXPIRY))

        permit.clean()

    def test_a_new_unsaved_permit_has_no_fleet_to_judge(self, centre):
        """Sin pk no hay M2M que leer: el modelo calla y la regla la aplica el
        formulario con la flota elegida."""
        permit = FlightPermission(
            cost_center=centre,
            purpose="photogrammetry",
            status="requested",
            location="Sector",
            area_type="unpopulated",
            valid_from=START,
            valid_until=EXPIRY,
        )

        permit.clean()


@pytest.mark.django_db
class TestItIsSaidBeforeItIsBroken:
    def test_the_aircraft_choice_shows_the_insurance_date(self, centre, operator):
        _aircraft("RPA-3696", EXPIRY)

        form = FlightPermissionForm()
        labels = [str(label) for _value, label in form.fields["aircraft_fleet"].choices]

        assert any("RPA-3696" in label and "2026-12-21" in label for label in labels)

    def test_an_aircraft_without_a_date_shows_no_insurance_text(self, centre, operator):
        _aircraft("RPA-NODATE", None)

        form = FlightPermissionForm()
        labels = [str(label) for _value, label in form.fields["aircraft_fleet"].choices]

        assert not any("seguro hasta" in label for label in labels)

    def test_the_end_date_help_states_the_rule_always(self):
        help_text = str(FlightPermissionForm().fields["valid_until"].help_text)

        assert "día anterior" in help_text

    def test_the_permit_page_states_the_latest_end_date(self, client, centre):
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="requested",
            location="Sector",
            area_type="unpopulated",
            valid_from=START,
            valid_until=date(2026, 12, 20),
        )
        permit.aircraft_fleet.add(_aircraft("RPA-3696", EXPIRY))
        admin = User.objects.create_superuser("i287", "i287@test.com", "pw")  # nosec B106
        client.force_login(admin)

        body = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "puede terminar el 2026-12-20 como máximo" in body

    def test_an_approved_permit_page_shows_no_such_note(self, client, centre):
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="approved",
            permission_number="6551",
            location="Sector",
            area_type="unpopulated",
            valid_from=START,
            valid_until=date(2026, 12, 20),
        )
        permit.aircraft_fleet.add(_aircraft("RPA-3696", EXPIRY))
        admin = User.objects.create_superuser("i287b", "i287b@test.com", "pw")  # nosec B106
        client.force_login(admin)

        body = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "como máximo" not in body
