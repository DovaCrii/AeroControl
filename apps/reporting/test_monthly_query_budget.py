"""LV-355 F0: presupuesto de consultas del informe mensual en vista previa.

Sin un `ReportRun` del período la pantalla llama a `builder.build()` completo en
cada GET, y el Dato Ejecutivo lo vuelve a hacer (§5 de
`docs/dev/informes-optimizacion.md`: «Medir»). Esto **mide el `build()` completo** y
fija el techo actual; no optimiza ni cachea nada.

El informe **congelado** sólo lee el payload y no se optimiza: lo vigila el
snapshot (`test_snapshot_monthly`), y aquí se fija que no consulta de más.

Techos medidos el 2026-10-26 sobre `origin/main`; no se aflojan para que pase un
cambio.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter
from apps.reporting.builder import build
from apps.reporting.models import ReportRun

PERIOD = date(2026, 8, 1)
CUTOFF = date(2026, 8, 31)
SMALL, LARGE = 2, 6

# Medido (segunda llamada, cachés tibias): `build()` son 32 consultas y no crecen con
# las faenas (agrega por `GROUP BY`/`prefetch_related`); la pantalla de vista previa
# suma sesión, permisos y plantilla: 42. El Dato Ejecutivo, 42: reconstruye lo mismo
# en su propio GET. Congelado, 10: sólo lee el `ReportRun`.
# LV-378: el número no cambió y se justifica: se quitó la consulta de conteos por
# faena (ahora salen de las filas de permisos) y se sumó la del informe del mes
# anterior para `payload.changes`; la reconstrucción de los vencidos tras el corte es
# una subconsulta dentro de la consulta de permisos, no una más.
BUILD_CEILING = {SMALL: 32, LARGE: 32}
PREVIEW_CEILING = {SMALL: 42, LARGE: 42}
BRIEF_CEILING = {SMALL: 42, LARGE: 42}
FROZEN_CEILING = 10


def _centres(start, stop):
    """Faenas que operan, cada una con un permiso vigente al corte."""
    for n in range(start, stop):
        centre = CostCenter.objects.create(
            code=f"F{n:02d}", name=f"Faena {n}", operates_flights=True
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=CUTOFF - timedelta(days=30),
            valid_until=CUTOFF + timedelta(days=10 + n),
        )
        # `created_at` es `auto_now_add`: se envejece para que el corte lo cuente.
        FlightPermission.objects.filter(pk=permit.pk).update(
            created_at="2026-07-15T12:00:00+00:00"
        )


def _count(call):
    """Consultas de la **segunda** llamada: la primera calienta cachés de proceso
    (`ContentType`, permisos) que no son costo del informe."""
    call()
    with CaptureQueriesContext(connection) as queries:
        call()
    return len(queries)


@pytest.fixture
def reader(client, db):
    user = User.objects.create_user("reader", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    client.force_login(user)
    return client


def _preview(client):
    return client.get(reverse("monthly-report"), {"period": "2026-08"})


def _brief(client):
    return client.get(reverse("monthly-report-brief"), {"period": "2026-08"})


@pytest.mark.django_db
class TestTheMonthlyPreviewQueryBudget:
    @pytest.mark.parametrize("centres", [SMALL, LARGE])
    def test_building_the_payload_has_a_ceiling(
        self, centres, django_assert_max_num_queries
    ):
        _centres(0, centres)
        build(PERIOD)  # calienta cachés de proceso

        with django_assert_max_num_queries(BUILD_CEILING[centres]):
            build(PERIOD)

    @pytest.mark.parametrize("centres", [SMALL, LARGE])
    def test_the_preview_page_has_a_ceiling(
        self, centres, reader, django_assert_max_num_queries
    ):
        _centres(0, centres)
        _preview(reader)

        with django_assert_max_num_queries(PREVIEW_CEILING[centres]):
            response = _preview(reader)

        assert response.status_code == 200
        assert response.context["run"] is None  # es vista previa, no congelado

    @pytest.mark.parametrize("centres", [SMALL, LARGE])
    def test_the_brief_preview_has_a_ceiling(
        self, centres, reader, django_assert_max_num_queries
    ):
        _centres(0, centres)
        _brief(reader)

        with django_assert_max_num_queries(BRIEF_CEILING[centres]):
            response = _brief(reader)

        assert response.status_code == 200

    def test_a_frozen_report_does_not_rebuild_anything(
        self, reader, django_assert_max_num_queries
    ):
        """El payload congelado **es** la caché del mes cerrado: la página no
        consulta cifras, sólo el `ReportRun`, el anterior y los permisos."""
        _centres(0, LARGE)
        ReportRun.objects.create(
            period=PERIOD,
            revision=0,
            generated_by="test",
            payload=build(PERIOD)[0],
        )
        _preview(reader)

        with django_assert_max_num_queries(FROZEN_CEILING):
            response = _preview(reader)

        assert response.context["run"] is not None

    def test_the_preview_cost_does_not_grow_with_the_cost_centres(self, reader):
        """Hoy es constante; si alguien agrega una consulta por faena, falla."""
        _centres(0, SMALL)
        small = _count(lambda: _preview(reader))
        _centres(SMALL, LARGE)
        large = _count(lambda: _preview(reader))

        assert large == small, (small, large)
