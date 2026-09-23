"""LV-248: el informe más corto, con lo esencial — y nada se pierde del papel.

Pedido del usuario el 2026-09-23: *"que el informe o reporte sea más corto, de lo
necesario con lo esencial, pero poder hacerlo automático"*. De lo que se le ofreció
recortar eligió **la nómina de operadores dentro de la tabla de permisos**.

⚠️ **Y la premisa con que se le ofreció estaba mal**, que es lo que vale dejar
escrito. Se le dijo que la nómina era "la causa directa de las hojas de más"; con
los datos de producción —11 vigentes y 3 en trámite— el recorte **solo** no bajaba
ni una hoja, y el anexo con la nómina sumaba una (6 → 7). Se midió, se le dijo, y
eligió mover además el ciclo de cuatro pasos al resumen. Tampoco alcanzaba: lo que
de verdad alargaba la tabla era que el folio **se partía en dos líneas** porque
`.rpt-table .c` pisaba la letra de 9 px del diseño. Restaurada, la fila baja de 45
a 27 px, y la sección de producción cabe en una hoja: **5 hojas más el anexo**.
"""

from datetime import timedelta

import pytest

from apps.reporting.views import MonthlyReportView


def _permit(folio, operators=4, in_force=True, aircraft=1):
    return {
        "folio": folio,
        "in_force": in_force,
        "cost_centre": "CC738",
        "operators": [f"Operador {n}" for n in range(operators)],
        "aircraft": [f"RPA-{n}" for n in range(aircraft)],
    }


def _production_shape():
    """La forma que tiene producción: 11 vigentes y 3 en trámite, cuatro
    operadores por permiso."""
    return {
        "permits": [_permit(f"JEJ-{n:03d}") for n in range(11)]
        + [_permit(f"JEJ-1{n:02d}", in_force=False) for n in range(3)]
    }


class TestProductionFitsInFewerSheets:
    def test_the_permits_section_takes_one_sheet(self):
        """Antes eran dos. Es la mitad del pedido que se ve al imprimir."""
        sheets = MonthlyReportView._sheets(_production_shape())

        assert len(sheets["permit_sheets"]) == 1

    def test_the_whole_document_is_five_sheets_plus_the_annex(self):
        sheets = MonthlyReportView._sheets(_production_shape())

        assert len(sheets["roster_sheets"]) == 1
        assert sheets["total_pages"] == 6
        # Las cuatro fijas y la de permisos, y el anexo al final.
        assert sheets["plan_page"] == 5
        assert sheets["roster_sheets"][0]["page"] == 6


class TestNothingLeavesThePaper:
    def test_the_annex_carries_every_permit_with_its_roster(self):
        """La nómina **cambia de lugar, no desaparece**: el anexo lleva vigentes y
        en trámite, en el mismo orden que la sección 2, para que un folio se
        encuentre en la misma posición en las dos hojas."""
        payload = _production_shape()

        sheets = MonthlyReportView._sheets(payload)

        rows = [row for sheet in sheets["roster_sheets"] for row in sheet["rows"]]
        assert [row["folio"] for row in rows] == [
            row["folio"] for row in payload["permits"]
        ]

    def test_without_any_name_there_is_no_annex(self):
        """Una hoja anexa de puros guiones le diría al lector que falta algo que
        nunca existió."""
        payload = {"permits": [_permit("JEJ-001", operators=0)]}

        sheets = MonthlyReportView._sheets(payload)

        assert sheets["roster_sheets"] == []
        assert sheets["total_pages"] == sheets["plan_page"]


@pytest.mark.django_db
class TestWhatThePagesSay:
    @pytest.fixture
    def report(self, client, admin_user):
        from django.utils import timezone

        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter, Operator

        # La vista previa del mes **en curso**, y no un mes cerrado: el informe
        # reconstruye la población al corte (`LV-233`), así que un permiso creado
        # hoy no existe en el de agosto — que es lo correcto, y lo que hizo fallar
        # la primera versión de este fixture.
        cutoff = timezone.localdate()
        centre = CostCenter.objects.create(
            code="CC738", name="Faena", operates_flights=True
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=cutoff - timedelta(days=30),
            valid_until=cutoff + timedelta(days=40),
        )
        for index, name in enumerate(
            ["Alexandra Márquez", "Javier Marin", "Francisca Fredes", "Kevin Palma"]
        ):
            permit.operators.add(
                Operator.objects.create(employee_id=f"E{index}", full_name=name)
            )
        client.force_login(admin_user)
        from django.urls import reverse

        return client.get(
            reverse("monthly-report"), {"period": f"{cutoff:%Y-%m}"}
        ).content.decode()

    def test_the_permit_table_says_how_many(self, report):
        assert "4 operadores" in report

    def test_the_names_are_in_the_annex(self, report):
        assert "Anexo · Operadores designados por permiso" in report
        assert "Alexandra Márquez" in report

    def test_the_cycle_moved_to_the_summary(self, report):
        """El ciclo de cuatro pasos sigue en el papel —es el trámite que fija el
        instructivo— pero como nota del resumen y no como bloque de la hoja 3."""
        assert "Ciclo del permiso de operación" in report
        assert "Ciclo de vigencia del permiso de operación" not in report
