"""LV-296: la fila de una faena cuyo permiso está aprobado pero aún no empieza.

Caso real (2026-10-08, `JEJ-2026-016`, CC684): aprobado el 8 con vigencia desde el 10.
El panel lo contaba bien como «aún no empieza», pero la tabla por faena mostraba la fila en
rojo con «Ninguno», como si la faena no tuviera nada. El conteo firmado no cambia
(`LV-258`); lo que cambia es lo que la fila dice.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance.kpis import permit_status_by_cost_center
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def centre(db):
    centre = CostCenter.objects.create(
        code="CC684", name="PMCHS", operates_flights=True
    )
    # Con la base vacía el panel muestra el onboarding y no la tabla por faena.
    Aircraft.objects.create(
        registration="RPA-1",
        type="RPA",
        model="M3",
        manufacturer="DJI",
        cost_center=centre,
    )
    return centre


def _permit(centre, start, end, status=FlightPermission.STATUS_APPROVED):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        permission_number="7218",
        location="Calama",
        area_type="unpopulated",
        valid_from=start,
        valid_until=end,
    )


def _row(code="CC684"):
    return next(
        r for r in permit_status_by_cost_center(TODAY) if r["cost_center"].code == code
    )


@pytest.mark.django_db
class TestTheRowSaysWhenItStarts:
    def test_the_row_carries_the_start_date(self, centre):
        start = TODAY + timedelta(days=2)
        _permit(centre, start, start + timedelta(days=90))

        row = _row()

        assert row["not_started"] == 1
        assert row["next_start"] == start

    def test_it_still_does_not_count_as_in_force(self, centre):
        """El indicador firmado no se mueve: `LV-258`."""
        start = TODAY + timedelta(days=2)
        _permit(centre, start, start + timedelta(days=90))

        assert _row()["in_force"] == 0

    def test_a_permit_in_force_has_no_start_date(self, centre):
        _permit(centre, TODAY - timedelta(days=5), TODAY + timedelta(days=60))

        assert _row()["next_start"] is None

    def test_the_dashboard_row_is_amber_with_the_date_not_critical_none(
        self, centre, admin_client
    ):
        start = TODAY + timedelta(days=2)
        _permit(centre, start, start + timedelta(days=90))

        html = admin_client.get(reverse("dashboard")).content.decode()
        marker = 'cc-chip me-2">CC684'
        row = html.split(marker)[1].split("</tr>")[0]

        assert start.strftime("%d/%m") in row
        tr_open = html[: html.index(marker)].rsplit("<tr", 1)[1].split(">")[0]
        assert "row-awaiting" in tr_open
        assert "row-critical" not in tr_open

    def test_a_centre_with_nothing_is_still_critical(self, centre, admin_client):
        html = admin_client.get(reverse("dashboard")).content.decode()
        marker = 'cc-chip me-2">CC684'

        tr_open = html[: html.index(marker)].rsplit("<tr", 1)[1].split(">")[0]
        assert "row-critical" in tr_open
