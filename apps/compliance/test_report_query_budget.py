"""LV-355 F0: presupuesto de consultas del Reporte de vigencia documental.

`docs/dev/informes-optimizacion.md` §5 anota que el Reporte hace «~3 o más
consultas por faena, ×2 por la comparación» y que **nunca se midió**. Esto mide y
fija el techo **actual**, sin optimizarlo todavía: el objetivo de la fase es que
una optimización posterior (agrupar por `cost_center`) se pueda demostrar bajando
el techo, y que una regresión que añada consultas por faena falle hoy.

El catastro ya tiene el suyo (`test_lv145_catastro_views`, 2 + 2) y no se toca.

Los techos son los **medidos** el 2026-10-26 sobre `origin/main`. No se aflojan
para que pase un cambio: si suben, se explica por qué en el PR.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.compliance.reports import build_compliance_report
from apps.registry.models import Aircraft, CostCenter

# Se mide con 2 y con 6 faenas: la diferencia es **el costo por faena**, que es lo
# que la optimización futura tiene que llevar a cero.
SMALL, LARGE = 2, 6

# Medido (segunda llamada, cachés tibias): armar el reporte cuesta 26 consultas con
# 2 faenas y 38 con 6, o sea 14 fijas y 3 por faena. La página lo arma dos veces
# (período y período anterior) y suma sesión, permisos y plantilla: 63 y 87, o sea
# 6 por faena.
BUILD_CEILING = {SMALL: 26, LARGE: 38}
PAGE_CEILING = {SMALL: 63, LARGE: 87}
BUILD_PER_CENTRE = 3
PAGE_PER_CENTRE = 6


def _centres(start, stop):
    """Faenas `start..stop-1`, cada una con una aeronave y un seguro."""
    doc_type = DocumentType.objects.get_or_create(code="SEG", name="Seguro")[0]
    aircraft_ct = ContentType.objects.get_for_model(Aircraft)
    today = timezone.localdate()
    for n in range(start, stop):
        centre = CostCenter.objects.create(code=f"F{n:02d}", name=f"Faena {n}")
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{n:03d}",
            type="Multirotor",
            model="M300",
            manufacturer="DJI",
            cost_center=centre,
        )
        Document.objects.create(
            title=f"seguro-{n}",
            doc_type=doc_type,
            content_type=aircraft_ct,
            object_id=aircraft.pk,
            file_path=f"seg/{n}.pdf",
            issue_date=date(2026, 1, 1),
            expiry_date=today + timedelta(days=5 + n),
        )


def _count(call):
    """Consultas de la **segunda** llamada: la primera calienta cachés de proceso
    (`ContentType`, permisos), que no son costo del reporte y harían depender el
    número del orden en que `-n auto` reparte los tests."""
    call()
    with CaptureQueriesContext(connection) as queries:
        call()
    return len(queries)


@pytest.fixture
def reader(client, db):
    user = User.objects.create_user("reader", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_document", content_type__app_label="compliance"
        )
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestTheComplianceReportQueryBudget:
    @pytest.mark.parametrize("centres", [SMALL, LARGE])
    def test_building_the_report_has_a_ceiling(
        self, centres, django_assert_max_num_queries
    ):
        _centres(0, centres)
        build_compliance_report()  # calienta cachés de proceso

        with django_assert_max_num_queries(BUILD_CEILING[centres]):
            build_compliance_report()

    @pytest.mark.parametrize("centres", [SMALL, LARGE])
    def test_the_page_with_its_comparison_has_a_ceiling(
        self, centres, reader, django_assert_max_num_queries
    ):
        """La página arma el reporte **dos veces** (período y período anterior)."""
        _centres(0, centres)
        reader.get(reverse("compliance-report"))  # calienta cachés de proceso

        with django_assert_max_num_queries(PAGE_CEILING[centres]):
            response = reader.get(reverse("compliance-report"))

        assert response.status_code == 200

    def test_the_cost_per_centre_is_bounded(self):
        """La pendiente, no sólo el total: cada faena de más no puede costar más
        de `BUILD_PER_CENTRE` consultas al armar el reporte."""
        _centres(0, SMALL)
        small = _count(build_compliance_report)
        _centres(SMALL, LARGE)
        large = _count(build_compliance_report)

        assert large - small <= BUILD_PER_CENTRE * (LARGE - SMALL), (small, large)

    def test_the_page_cost_per_centre_is_bounded(self, reader):
        _centres(0, SMALL)
        small = _count(lambda: reader.get(reverse("compliance-report")))
        _centres(SMALL, LARGE)
        large = _count(lambda: reader.get(reverse("compliance-report")))

        assert large - small <= PAGE_PER_CENTRE * (LARGE - SMALL), (small, large)
