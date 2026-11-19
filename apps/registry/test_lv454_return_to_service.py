"""LV-454: «Volver a servicio» para una aeronave que quedó «En mantenimiento».

Sólo la sacaban de ahí anular el ingreso a taller y cerrar la mantención; si el ingreso ya
se había quitado, el equipo seguía «En mantenimiento» en la lista y no había botón. Ahora
`Aircraft.return_to_service` lo hace a mano, salvo que una mantención activa en taller lo
retenga (entonces se rechaza y se apunta a esa mantención). Datos ficticios.
"""

import re
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import Aircraft, CostCenter, ResourceMovementLog

CHANGE = "change_aircraft"
VIEW = "view_aircraft"


def _aircraft(registration="RPA-454", **extra):
    extra.setdefault("status", "maintenance")
    extra.setdefault("current_location", "maintenance")
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        serial_number=f"SN-{registration}",
        **extra,
    )


def _record(aircraft, status="at_workshop", **extra):
    return MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="corrective",
        status=status,
        scheduled_date=date(2026, 1, 10),
        description="Revision ficticia",
        **extra,
    )


def _url(aircraft):
    return reverse("aircraft-return-to-service", args=[aircraft.pk])


def _rows(response, aircraft):
    """Sólo la fila de esa aeronave: el resto de la lista comparte vocabulario."""
    content = response.content.decode()
    match = re.search(rf'<tr data-pk="{aircraft.pk}">.*?</tr>', content, re.S)
    return match.group(0) if match else ""


@pytest.mark.django_db
class TestModel:
    def test_a_free_aircraft_in_maintenance_goes_back_to_headquarters(self):
        aircraft = _aircraft()
        assert aircraft.return_to_service() is True
        aircraft.refresh_from_db()
        assert (aircraft.status, aircraft.current_location) == (
            "active",
            "headquarters",
        )
        assert aircraft.current_site is None

    def test_a_held_aircraft_is_refused_and_untouched(self):
        aircraft = _aircraft()
        record = _record(aircraft)
        with pytest.raises(ValidationError) as caught:
            aircraft.return_to_service()
        assert str(record) in " ".join(caught.value.messages)
        aircraft.refresh_from_db()
        assert (aircraft.status, aircraft.current_location) == (
            "maintenance",
            "maintenance",
        )

    def test_only_a_workshop_status_holds_it(self):
        aircraft = _aircraft()
        _record(aircraft, status="completed")
        _record(aircraft, status="at_workshop", is_active=False)
        assert aircraft.return_to_service() is True

    def test_it_is_idempotent(self):
        aircraft = _aircraft(status="active", current_location="headquarters")
        assert aircraft.return_to_service() is False
        aircraft.refresh_from_db()
        assert aircraft.status == "active"

    def test_the_movement_is_logged_with_the_author(self):
        aircraft = _aircraft()
        user = login_as(CHANGE).user
        aircraft.return_to_service(user=user)
        log = ResourceMovementLog.objects.filter(
            resource_kind="aircraft", resource_id=aircraft.pk
        ).latest("sequence")
        assert log.changed_by_user == user


@pytest.mark.django_db
class TestView:
    def test_post_returns_it_audits_and_redirects_to_the_file(self):
        aircraft = _aircraft()
        client = login_as(CHANGE)
        response = client.post(_url(aircraft))
        assert response.status_code == 302
        assert response["Location"] == reverse("aircraft-detail", args=[aircraft.pk])
        aircraft.refresh_from_db()
        assert aircraft.status == "active"
        assert AuditEvent.objects.filter(action="returned_to_service").exists()

    def test_a_safe_next_is_honoured_and_an_external_one_is_not(self):
        aircraft = _aircraft()
        client = login_as(CHANGE)
        response = client.post(_url(aircraft), {"next": "https://evil.example/"})
        assert response["Location"] == reverse("aircraft-detail", args=[aircraft.pk])
        other = _aircraft("RPA-454B")
        response = client.post(_url(other), {"next": reverse("aircraft-list")})
        assert response["Location"] == reverse("aircraft-list")

    def test_a_held_aircraft_stays_and_the_message_names_the_record(self):
        aircraft = _aircraft()
        record = _record(aircraft)
        client = login_as(VIEW, CHANGE)
        response = client.post(_url(aircraft), follow=True)
        aircraft.refresh_from_db()
        assert aircraft.status == "maintenance"
        assert str(record) in response.content.decode()

    def test_without_the_permission_it_is_403(self):
        aircraft = _aircraft()
        response = login_as(VIEW).post(_url(aircraft))
        assert response.status_code == 403
        aircraft.refresh_from_db()
        assert aircraft.status == "maintenance"

    def test_get_is_not_allowed(self):
        aircraft = _aircraft()
        assert login_as(CHANGE).get(_url(aircraft)).status_code == 405

    def test_another_tenant_aircraft_is_a_404_and_untouched(self):
        mine = OperationalTenant.objects.create(name="Mi empresa", slug="mi-e")
        theirs = OperationalTenant.objects.create(name="Otra empresa", slug="otra-e")
        center = CostCenter.objects.create(code="CC-B", name="Faena B", tenant=theirs)
        aircraft = _aircraft(cost_center=center, tenant=theirs)
        client = login_as(CHANGE, member_of=mine)
        assert client.post(_url(aircraft)).status_code == 404
        aircraft.refresh_from_db()
        assert aircraft.status == "maintenance"


@pytest.mark.django_db
class TestButtons:
    def _list(self, *perms):
        return login_as(VIEW, *perms).get(reverse("aircraft-list"))

    def _detail(self, aircraft, *perms):
        return login_as(VIEW, *perms).get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

    def test_the_list_offers_the_button_on_a_free_aircraft_in_maintenance(self):
        aircraft = _aircraft()
        row = _rows(self._list(CHANGE), aircraft)
        assert _url(aircraft) in row
        assert "data-confirm" in row

    def test_the_list_hides_it_without_the_permission_or_when_not_in_maintenance(self):
        aircraft = _aircraft()
        fine = _aircraft("RPA-454C", status="active", current_location="headquarters")
        response = self._list()
        assert _url(aircraft) not in _rows(response, aircraft)
        response = self._list(CHANGE)
        assert _url(fine) not in _rows(response, fine)

    def test_the_list_links_the_open_maintenance_instead_of_the_button(self):
        aircraft = _aircraft()
        record = _record(aircraft)
        row = _rows(self._list(CHANGE, "view_maintenancerecord"), aircraft)
        assert _url(aircraft) not in row
        assert reverse("maintenance-detail", args=[record.pk]) in row

    def test_the_list_does_not_add_a_query_per_aircraft(
        self, django_assert_max_num_queries
    ):
        for i in range(6):
            aircraft = _aircraft(f"RPA-45{i}X")
            _record(aircraft)
        client = login_as(VIEW, CHANGE, "view_maintenancerecord")
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as few:
            client.get(reverse("aircraft-list"))
        for i in range(6):
            aircraft = _aircraft(f"RPA-45{i}Y")
            _record(aircraft)
        with CaptureQueriesContext(connection) as many:
            client.get(reverse("aircraft-list"))
        assert len(many) == len(few)

    def test_the_file_offers_the_button_or_the_link(self):
        aircraft = _aircraft()
        content = self._detail(aircraft, CHANGE).content.decode()
        assert "data-return-to-service" in content
        assert _url(aircraft) in content
        record = _record(aircraft)
        content = self._detail(
            aircraft, CHANGE, "view_maintenancerecord"
        ).content.decode()
        assert "data-return-to-service" not in content
        assert "data-workshop-hold" in content
        assert reverse("maintenance-detail", args=[record.pk]) in content

    def test_the_file_hides_it_without_the_permission(self):
        aircraft = _aircraft()
        content = self._detail(aircraft).content.decode()
        assert "data-return-to-service" not in content
        assert _url(aircraft) not in content
