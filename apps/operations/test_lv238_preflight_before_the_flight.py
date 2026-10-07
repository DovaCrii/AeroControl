"""LV-238: el chequeo prevuelo se puede hacer y firmar ANTES de volar.

Hallazgo de la revisión del 2026-09-21 y decisión del usuario del 2026-10-07: el
chequeo sólo existía colgado de un registro de vuelo, y la bitácora se escribe al
volver —a veces al día siguiente—, así que la firma de un chequeo *previo* quedaba con
fecha **posterior al despegue**. Como evidencia ante una fiscalización, eso es justo lo
que `UX-29` decía venir a resolver.

Ahora un chequeo puede nacer ligado a un **permiso y una aeronave de su flota**, se
firma cuando se hace, y cuando el vuelo se registre lo **adopta** (misma aeronave,
mismo permiso, mismo día).
"""

from datetime import date, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.models import (
    FlightPermission,
    FlightRecord,
    PreflightAnswer,
    PreflightCheck,
    PreflightChecklist,
    PreflightChecklistItem,
)
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def aircraft(centre):
    return Aircraft.objects.create(
        registration="RPA-2019",
        type="RPA",
        model="Mavic 3 Enterprise",
        manufacturer="DJI",
        cost_center=centre,
    )


@pytest.fixture
def permit(centre, aircraft):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number="P-1",
        location="Sector 3",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=10),
        valid_until=TODAY + timedelta(days=60),
    )
    permit.aircraft_fleet.add(aircraft)
    return permit


@pytest.fixture
def checklist(db):
    checklist = PreflightChecklist.objects.create(name="General")
    for order, text in enumerate(("Hélices", "Batería")):
        PreflightChecklistItem.objects.create(
            checklist=checklist, text=text, order=order
        )
    return checklist


@pytest.fixture
def pilot(centre):
    return Operator.objects.create(full_name="Piloto", cost_center=centre)


def _flight(permit, aircraft, pilot, day=TODAY):
    return FlightRecord.objects.create(
        permission=permit,
        actual_date=day,
        aircraft=aircraft,
        pilot=pilot,
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
    )


def _start(permit, aircraft, checklist, day=TODAY):
    return PreflightCheck.open_from_checklist(
        checklist, permission=permit, aircraft=aircraft, planned_date=day
    )


@pytest.mark.django_db
class TestACheckCanExistWithoutAFlight:
    def test_it_is_created_with_its_items_blank(self, permit, aircraft, checklist):
        check = _start(permit, aircraft, checklist)

        assert check.flight_record is None
        assert check.permission == permit
        assert [a.text for a in check.answers.all()] == ["Hélices", "Batería"]
        assert {a.value for a in check.answers.all()} == {PreflightAnswer.PENDING}

    def test_a_check_with_no_owner_at_all_cannot_exist(self, checklist):
        """La nulabilidad de `flight_record` no deja nacer chequeos huérfanos."""
        with pytest.raises(IntegrityError), transaction.atomic():
            PreflightCheck.objects.create(checklist=checklist, checklist_name="x")

    def test_a_check_with_only_a_permission_is_not_enough(self, permit, checklist):
        with pytest.raises(IntegrityError), transaction.atomic():
            PreflightCheck.objects.create(
                checklist=checklist, checklist_name="x", permission=permit
            )

    def test_signing_before_the_flight_keeps_the_real_time(
        self, permit, aircraft, checklist, pilot
    ):
        """El punto de todo el cambio: la firma queda **antes** del vuelo."""
        check = _start(permit, aircraft, checklist)
        check.answers.update(value=PreflightAnswer.OK)
        user = login_as().user

        check.sign(user)
        flight = _flight(permit, aircraft, pilot)

        assert check.signed_at <= flight.created_at

    def test_the_text_of_the_items_is_still_copied(self, permit, aircraft, checklist):
        check = _start(permit, aircraft, checklist)
        checklist.items.update(text="Cambiado después")

        assert [a.text for a in check.answers.all()] == ["Hélices", "Batería"]


@pytest.mark.django_db
class TestTheFlightAdoptsItsCheck:
    def test_a_flight_registered_afterwards_adopts_the_check(
        self, permit, aircraft, checklist, pilot
    ):
        check = _start(permit, aircraft, checklist)

        flight = _flight(permit, aircraft, pilot)
        adopted = PreflightCheck.adopt_for(flight)

        check.refresh_from_db()
        assert adopted == check
        assert check.flight_record == flight

    def test_the_creation_view_does_it_without_anyone_asking(
        self, permit, aircraft, checklist, pilot, client
    ):
        # El formulario sólo ofrece pilotos del padrón del permiso.
        permit.operators.add(pilot)
        check = _start(permit, aircraft, checklist)
        client = login_as(
            "add_flightrecord", "view_flightrecord", "view_flightpermission"
        )

        response = client.post(
            reverse("record-create"),
            {
                "permission": str(permit.pk),
                "actual_date": TODAY.isoformat(),
                "aircraft": str(aircraft.pk),
                "pilot": str(pilot.pk),
                "departure_time": "09:00",
                "arrival_time": "10:00",
            },
        )

        errors = (
            response.context["form"].errors if response.status_code == 200 else None
        )
        assert response.status_code == 302, errors
        check.refresh_from_db()
        assert check.flight_record is not None
        assert check.flight_record.actual_date == TODAY

    def test_another_day_is_not_adopted(self, permit, aircraft, checklist, pilot):
        check = _start(permit, aircraft, checklist, day=TODAY + timedelta(days=1))

        PreflightCheck.adopt_for(_flight(permit, aircraft, pilot))

        check.refresh_from_db()
        assert check.flight_record is None

    def test_another_aircraft_is_not_adopted(
        self, permit, aircraft, checklist, pilot, centre
    ):
        other = Aircraft.objects.create(
            registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
        )
        permit.aircraft_fleet.add(other)
        check = _start(permit, aircraft, checklist)

        PreflightCheck.adopt_for(_flight(permit, other, pilot))

        check.refresh_from_db()
        assert check.flight_record is None

    def test_a_flight_that_already_has_a_check_does_not_get_a_second(
        self, permit, aircraft, checklist, pilot
    ):
        flight = _flight(permit, aircraft, pilot)
        PreflightCheck.open_from_checklist(checklist, flight_record=flight)
        loose = _start(permit, aircraft, checklist)

        assert PreflightCheck.adopt_for(flight) is None

        loose.refresh_from_db()
        assert loose.flight_record is None

    def test_two_flights_the_same_day_take_the_checks_in_the_order_they_were_made(
        self, permit, aircraft, checklist, pilot
    ):
        first = _start(permit, aircraft, checklist)
        second = _start(permit, aircraft, checklist)

        one = PreflightCheck.adopt_for(_flight(permit, aircraft, pilot))
        two = PreflightCheck.adopt_for(_flight(permit, aircraft, pilot))

        assert (one, two) == (first, second)


@pytest.mark.django_db
class TestStartingFromThePermit:
    def _start_url(self, permit):
        return reverse("preflight-start", args=[permit.pk])

    def test_it_creates_the_check_and_opens_it(self, permit, aircraft, checklist):
        client = login_as("add_flightrecord", "change_flightrecord")

        response = client.post(
            self._start_url(permit),
            {"aircraft": str(aircraft.pk), "planned_date": TODAY.isoformat()},
        )

        check = PreflightCheck.objects.get()
        assert response.status_code == 302
        assert response.url == reverse("preflight-standalone", args=[check.pk])
        assert check.permission == permit
        assert check.aircraft == aircraft
        assert check.planned_date == TODAY

    def test_without_the_permission_it_is_forbidden(self, permit, aircraft, checklist):
        client = login_as("view_flightrecord")

        response = client.post(self._start_url(permit), {"aircraft": str(aircraft.pk)})

        assert response.status_code == 403
        assert PreflightCheck.objects.count() == 0

    def test_an_aircraft_the_permit_does_not_cover_is_refused(self, permit, checklist):
        stranger = Aircraft.objects.create(
            registration="RPA-9999", type="RPA", model="M3", manufacturer="DJI"
        )
        client = login_as("add_flightrecord")

        response = client.post(self._start_url(permit), {"aircraft": str(stranger.pk)})

        assert response.status_code == 404
        assert PreflightCheck.objects.count() == 0

    def test_with_no_checklist_nothing_is_created_and_it_says_so(
        self, permit, aircraft
    ):
        client = login_as("add_flightrecord", "view_flightpermission")

        response = client.post(
            self._start_url(permit), {"aircraft": str(aircraft.pk)}, follow=True
        )

        assert PreflightCheck.objects.count() == 0
        assert "No hay ninguna lista de chequeo prevuelo" in response.content.decode()

    def test_a_bad_date_falls_back_to_today(self, permit, aircraft, checklist):
        client = login_as("add_flightrecord", "change_flightrecord")

        client.post(
            self._start_url(permit),
            {"aircraft": str(aircraft.pk), "planned_date": "mañana"},
        )

        assert PreflightCheck.objects.get().planned_date == TODAY

    def test_get_is_not_allowed(self, permit):
        client = login_as("add_flightrecord")

        assert client.get(self._start_url(permit)).status_code == 405


@pytest.mark.django_db
class TestTheStandaloneScreen:
    def _check(self, permit, aircraft, checklist):
        return _start(permit, aircraft, checklist)

    def test_it_shows_the_check_with_its_header(self, permit, aircraft, checklist):
        check = self._check(permit, aircraft, checklist)
        client = login_as("change_flightrecord")

        response = client.get(reverse("preflight-standalone", args=[check.pk]))
        body = response.content.decode()

        assert response.status_code == 200
        assert "Hélices" in body and "Batería" in body
        assert "RPA-2019" in body
        # La firma apunta a la URL propia, no a la del vuelo (que no existe).
        assert reverse("preflight-standalone-sign", args=[check.pk]) in body

    def test_it_needs_the_permission(self, permit, aircraft, checklist):
        check = self._check(permit, aircraft, checklist)

        response = login_as("view_flightrecord").get(
            reverse("preflight-standalone", args=[check.pk])
        )

        assert response.status_code == 403

    def test_answers_are_saved_and_unanswered_is_not_offered(
        self, permit, aircraft, checklist
    ):
        check = self._check(permit, aircraft, checklist)
        first, second = check.answers.all()
        client = login_as("change_flightrecord")

        client.post(
            reverse("preflight-standalone", args=[check.pk]),
            {
                f"value-{first.pk}": "ok",
                f"value-{second.pk}": "not_ok",
                f"comment-{second.pk}": "Desgaste",
            },
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.value, second.value) == ("ok", "not_ok")
        assert second.comment == "Desgaste"
        body = client.get(
            reverse("preflight-standalone", args=[check.pk])
        ).content.decode()
        assert 'value="pending"' not in body

    def test_signing_needs_every_item_answered(self, permit, aircraft, checklist):
        check = self._check(permit, aircraft, checklist)
        client = login_as("change_flightrecord")

        client.post(reverse("preflight-standalone-sign", args=[check.pk]))

        check.refresh_from_db()
        assert not check.is_signed

    def test_a_signed_check_is_frozen(self, permit, aircraft, checklist):
        check = self._check(permit, aircraft, checklist)
        check.answers.update(value=PreflightAnswer.OK)
        client = login_as("change_flightrecord")
        client.post(reverse("preflight-standalone-sign", args=[check.pk]))
        answer = check.answers.first()

        client.post(
            reverse("preflight-standalone", args=[check.pk]),
            {f"value-{answer.pk}": "not_ok"},
        )

        answer.refresh_from_db()
        check.refresh_from_db()
        assert check.is_signed
        assert answer.value == PreflightAnswer.OK

    def test_signing_records_who_and_when(self, permit, aircraft, checklist):
        check = self._check(permit, aircraft, checklist)
        check.answers.update(value=PreflightAnswer.OK)
        client = login_as("change_flightrecord")

        client.post(reverse("preflight-standalone-sign", args=[check.pk]))

        check.refresh_from_db()
        assert check.signed_by == client.user
        assert check.signed_at is not None


@pytest.mark.django_db
class TestThePermitPageOffersIt:
    def _body(self, permit, *perms):
        client = login_as("view_flightpermission", *perms)
        return client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

    def test_an_approved_permit_offers_to_start_one(self, permit, checklist):
        body = self._body(permit, "add_flightrecord")

        assert reverse("preflight-start", args=[permit.pk]) in body
        assert "Empezar antes de volar" in body

    def test_without_the_flight_permission_it_does_not_offer_it(
        self, permit, checklist
    ):
        body = self._body(permit)

        assert reverse("preflight-start", args=[permit.pk]) not in body

    def test_a_requested_permit_does_not_offer_it(self, permit, checklist):
        """Un permiso solicitado todavía no autoriza a volar: no hay nada que
        chequear antes de un vuelo que no se puede hacer."""
        FlightPermission.objects.filter(pk=permit.pk).update(status="requested")
        permit.refresh_from_db()

        body = self._body(permit, "add_flightrecord")

        assert reverse("preflight-start", args=[permit.pk]) not in body

    def test_the_existing_checks_are_listed_with_their_state(
        self, permit, aircraft, checklist, pilot
    ):
        signed = _start(permit, aircraft, checklist)
        signed.answers.update(value=PreflightAnswer.OK)
        signed.sign(login_as().user)
        _start(permit, aircraft, checklist, day=TODAY + timedelta(days=1))
        PreflightCheck.adopt_for(_flight(permit, aircraft, pilot))

        body = self._body(permit, "add_flightrecord")

        assert "Firmado" in body
        assert "Sin firmar" in body
        assert "Aún sin vuelo" in body


@pytest.mark.django_db
class TestTheExistingFlightFlowIsUntouched:
    def test_the_check_of_a_flight_is_still_created_when_opened(
        self, permit, aircraft, checklist, pilot
    ):
        flight = _flight(permit, aircraft, pilot)
        client = login_as("view_flightrecord", "change_flightrecord")

        response = client.get(reverse("preflight-check", args=[flight.pk]))

        assert response.status_code == 200
        assert flight.preflight_check.answers.count() == 2
        assert flight.preflight_check.permission is None

    def test_the_flight_screen_header_still_shows_pilot_and_date(
        self, permit, aircraft, checklist, pilot
    ):
        flight = _flight(permit, aircraft, pilot)
        client = login_as("view_flightrecord", "change_flightrecord")

        body = client.get(reverse("preflight-check", args=[flight.pk])).content.decode()

        assert "Piloto" in body
        assert date.today().strftime("%d-%m-%Y") in body
