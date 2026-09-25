"""LV-258: un permiso aprobado que todavía no empieza no está vigente.

`permit_status_by_cost_center` contaba como vigente todo permiso aprobado cuya
fecha de término no había pasado, sin mirar si ya había **empezado**. Lo destapó
la hoja 3 del informe mensual, que en el demo decía 12 vigentes en la fila de
CC738 y 11 en el total: la diferencia era `JEJ-2026-003`, aprobado para arrancar
el 29 de septiembre.

Lo grave no es la suma: una faena cuyo **único** permiso todavía no empieza
salía con permiso vigente, fuera de la tarjeta «Faenas sin permiso» del panel
(`LV-246`) y del indicador que va firmado a la DGAC. `permit_counts` ya separaba
ese caso como `not_started` desde `LV-233`; la tabla por faena no.
"""

from datetime import date, timedelta

import pytest

from apps.compliance.kpis import permit_counts, permit_status_by_cost_center
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = date(2026, 9, 15)


def _centre(code):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _approved(centre, valid_from, valid_until):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number=f"P-258-{FlightPermission.objects.count()}",
        location="Sector",
        area_type="unpopulated",
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _row(code):
    return next(
        row
        for row in permit_status_by_cost_center(TODAY)
        if row["cost_center"].code == code
    )


@pytest.mark.django_db
class TestAPermitThatHasNotStarted:
    def test_is_not_counted_as_in_force(self):
        centre = _centre("CC258")
        _approved(centre, TODAY + timedelta(days=14), TODAY + timedelta(days=80))

        row = _row("CC258")

        assert row["in_force"] == 0
        assert row["not_started"] == 1

    def test_does_not_set_the_next_expiry_nor_the_soon_count(self):
        """La próxima renovación es la del permiso que **cubre** hoy. Uno que
        todavía no empieza no deja de cubrir nada."""
        centre = _centre("CC258")
        _approved(centre, TODAY + timedelta(days=5), TODAY + timedelta(days=20))

        row = _row("CC258")

        assert row["next_expiry"] is None
        assert row["soon"] == 0

    def test_a_permit_already_running_still_counts(self):
        """El contrapeso: el filtro nuevo no puede vaciar la columna."""
        centre = _centre("CC258")
        _approved(centre, TODAY - timedelta(days=10), TODAY + timedelta(days=20))
        _approved(centre, TODAY + timedelta(days=21), TODAY + timedelta(days=90))

        row = _row("CC258")

        assert row["in_force"] == 1
        assert row["not_started"] == 1
        assert row["next_expiry"] == TODAY + timedelta(days=20)

    def test_the_table_and_the_counts_agree(self):
        """La fila por faena y `permit_counts` responden lo mismo sobre la misma
        faena — son dos lecturas del mismo hecho, y la hoja 3 del informe las
        pone una encima de la otra."""
        centre = _centre("CC258")
        _approved(centre, TODAY - timedelta(days=10), TODAY + timedelta(days=20))
        _approved(centre, TODAY + timedelta(days=3), TODAY + timedelta(days=60))

        counts = permit_counts(TODAY, centre)

        assert _row("CC258")["in_force"] == counts["in_force"] == 1
        assert _row("CC258")["not_started"] == counts["not_started"] == 1


@pytest.mark.django_db
class TestTheCostCentreWithoutPermitIsDeclared:
    def test_the_panel_lists_it_among_those_without_permit(self, admin_client):
        """El caso que importa: su único permiso arranca la semana próxima, así
        que hoy no puede volar y el panel tiene que decirlo."""
        from django.urls import reverse
        from django.utils import timezone

        from apps.registry.models import Aircraft

        today = timezone.localdate()
        centre = _centre("CC259")
        _approved(centre, today + timedelta(days=7), today + timedelta(days=60))
        # Sin flota, el panel muestra la pantalla de primeros pasos.
        Aircraft.objects.create(
            registration="RPA-2580", type="RPA", model="M3", manufacturer="DJI"
        )

        response = admin_client.get(reverse("dashboard"))

        rows = {
            row["cost_center"].code: row
            for row in response.context["permit_status_rows"]
        }
        assert rows["CC259"]["in_force"] == 0
        assert response.context["cost_centres_without_permit"] >= 1
