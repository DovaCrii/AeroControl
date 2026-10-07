"""LV-290: «Registro de operaciones», la pantalla de la DGAC dentro de AeroControl.

Pedido del usuario (2026-10-07, con la captura del portal): *«así se registran los
vuelos ahora en la DGAC… sería importante sumar el mismo formato»*. No hay modelo
nuevo: una operación es un `FlightRecord`, así que el alta tiene que pasar por las
**mismas reglas** que el alta de siempre.
"""

from datetime import time, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.compliance.forms import _signature_matches
from apps.compliance.models import DocumentType
from apps.core.testing import login_as
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
READ = ("view_flightpermission", "view_flightrecord")


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def aircraft(centre):
    return Aircraft.objects.create(
        registration="RPA-2019",
        serial_number="SN-123456",
        type="RPA",
        model="Mavic 3 Enterprise",
        manufacturer="DJI",
        cost_center=centre,
    )


@pytest.fixture
def pilot(centre):
    return Operator.objects.create(
        full_name="Piloto Uno", employee_id="E-1", cost_center=centre
    )


@pytest.fixture
def permit(centre, aircraft, pilot):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number="DGAC-0042",
        location="Sector 3",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=10),
        valid_until=TODAY + timedelta(days=60),
    )
    permit.aircraft_fleet.add(aircraft)
    permit.operators.add(pilot)
    return permit


def _url(permit):
    return reverse("permission-operations", args=[permit.pk])


def _payload(aircraft, pilot, **over):
    data = {
        "actual_date": TODAY.isoformat(),
        "departure_time": "09:00",
        "arrival_time": "10:30",
        "pilot": str(pilot.pk),
        "aircraft": str(aircraft.pk),
    }
    data.update(over)
    return data


@pytest.mark.django_db
class TestTheScreen:
    def test_it_shows_the_header_of_the_portal(self, permit):
        response = login_as(*READ).get(_url(permit))

        assert response.status_code == 200
        html = response.content.decode()
        assert "DGAC-0042" in html
        assert "J.E.J." in html
        assert (TODAY - timedelta(days=10)).strftime("%d/%m/%Y") in html

    def test_it_lists_the_registered_operations_with_the_serial_number(
        self, permit, aircraft, pilot
    ):
        FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            aircraft=aircraft,
            pilot=pilot,
            departure_time=time(9, 0),
            arrival_time=time(10, 0),
        )

        html = login_as(*READ).get(_url(permit)).content.decode()

        assert "SN-123456" in html
        assert "Piloto Uno" in html

    def test_without_view_permission_it_is_forbidden(self, permit):
        assert login_as().get(_url(permit)).status_code == 403

    def test_another_tenant_cannot_open_it(self, permit):
        from apps.core.models import OperationalTenant

        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        client = login_as(*READ, member_of=other)

        assert client.get(_url(permit)).status_code == 404

    def test_the_permit_card_links_to_it(self, permit):
        html = (
            login_as(*READ)
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert _url(permit) in html


@pytest.mark.django_db
class TestRegisteringAnOperation:
    def test_it_creates_the_flight_record_and_comes_back(self, permit, aircraft, pilot):
        client = login_as(*READ, "add_flightrecord")

        response = client.post(_url(permit), _payload(aircraft, pilot))

        assert response.status_code == 302
        assert response.url == _url(permit)
        record = FlightRecord.objects.get()
        assert record.permission == permit
        assert record.pilot == pilot
        assert record.arrival_time == time(10, 30)

    def test_the_url_decides_the_permit_not_the_form(self, permit, aircraft, pilot):
        other = FlightPermission.objects.create(
            cost_center=permit.cost_center,
            purpose="x",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=5),
            location="Y",
            area_type="unpopulated",
        )
        client = login_as(*READ, "add_flightrecord")

        client.post(_url(permit), _payload(aircraft, pilot, permission=str(other.pk)))

        assert FlightRecord.objects.get().permission == permit

    def test_without_add_permission_it_is_forbidden_and_writes_nothing(
        self, permit, aircraft, pilot
    ):
        response = login_as(*READ).post(_url(permit), _payload(aircraft, pilot))

        assert response.status_code == 403
        assert not FlightRecord.objects.exists()

    def test_the_form_is_not_offered_without_add_permission(self, permit):
        html = login_as(*READ).get(_url(permit)).content.decode()

        assert 'id="operation-form"' not in html

    def test_arrival_must_be_after_departure(self, permit, aircraft, pilot):
        client = login_as(*READ, "add_flightrecord")

        response = client.post(
            _url(permit),
            _payload(aircraft, pilot, departure_time="10:00", arrival_time="09:00"),
        )

        assert response.status_code == 200
        assert not FlightRecord.objects.exists()

    def test_the_date_must_be_inside_the_authorized_period(
        self, permit, aircraft, pilot
    ):
        outside = (permit.valid_until + timedelta(days=3)).isoformat()
        client = login_as(*READ, "add_flightrecord")

        response = client.post(
            _url(permit), _payload(aircraft, pilot, actual_date=outside)
        )

        assert response.status_code == 200
        assert not FlightRecord.objects.exists()

    def test_an_operator_outside_the_permit_roster_is_refused(
        self, permit, aircraft, centre
    ):
        stranger = Operator.objects.create(
            full_name="Ajeno", employee_id="E-2", cost_center=centre
        )
        client = login_as(*READ, "add_flightrecord")

        response = client.post(_url(permit), _payload(aircraft, stranger))

        assert response.status_code == 200
        assert not FlightRecord.objects.exists()


@pytest.mark.django_db
class TestArchivingFromTheTable:
    def _record(self, permit, aircraft, pilot):
        return FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            aircraft=aircraft,
            pilot=pilot,
            departure_time=time(9, 0),
            arrival_time=time(10, 0),
        )

    def test_it_returns_to_the_screen_it_came_from(self, permit, aircraft, pilot):
        record = self._record(permit, aircraft, pilot)
        client = login_as(*READ, "delete_flightrecord")

        response = client.post(
            reverse("record-delete", args=[record.pk]), {"next": _url(permit)}
        )

        assert response.url == _url(permit)
        record.refresh_from_db()
        assert record.is_active is False

    def test_a_foreign_destination_is_ignored(self, permit, aircraft, pilot):
        record = self._record(permit, aircraft, pilot)
        client = login_as(*READ, "delete_flightrecord")

        response = client.post(
            reverse("record-delete", args=[record.pk]),
            {"next": "https://evil.example/"},
        )

        assert response.url == reverse("record-list")


@pytest.mark.django_db
class TestTheTextFlightLog:
    def test_the_document_type_exists_in_the_dgac_category(self):
        kind = DocumentType.objects.get(code="flight-log-txt")

        assert kind.category == DocumentType.CATEGORY_DGAC
        assert kind.requires_expiry is False
        assert kind.is_operational_record is False

    def test_the_upload_shortcut_is_offered_with_the_type_preselected(self, permit):
        kind = DocumentType.objects.get(code="flight-log-txt")
        client = login_as(*READ, "add_document")

        html = client.get(_url(permit)).content.decode()

        assert f"doc_type={kind.pk}" in html
        assert ".TXT" in html

    def test_a_plain_text_file_is_accepted(self):
        upload = SimpleUploadedFile("vuelo.txt", b"2026-10-07;09:00;10:30\n")

        assert _signature_matches(upload, "txt") is True
        assert upload.read() == b"2026-10-07;09:00;10:30\n"

    def test_a_file_with_nul_bytes_posing_as_text_is_refused(self):
        upload = SimpleUploadedFile("vuelo.txt", b"MZ\x00\x00binary")

        assert _signature_matches(upload, "txt") is False
