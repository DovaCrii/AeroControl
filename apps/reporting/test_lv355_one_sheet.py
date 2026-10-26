"""LV-355 F2: una sola cabecera y un solo papel (A4) en los informes operativos.

Antes: tres sistemas de cabecera (la `Letterhead` de reportlab, `_print_head`/
`_print_foot` de LV-319 y `_head`/`_foot` del A4 mensual) y tres tamaños de papel
(Carta, Carta horizontal y A4). Ahora dos sistemas —el operativo y el de la DGAC,
que **no se toca**— y un papel. Lo que se fija:

- el PDF del Reporte es A4 vertical y el del catastro A4 horizontal, medidos con
  `pypdf` (método sin navegador, como LV-263);
- la pantalla del catastro lleva la misma cabecera y pie de papel que el Reporte;
- el universo de cada tabla y la fecha de cada cifra de permisos están escritos;
- y **ninguna cifra cambió**: el snapshot del mensual (`test_snapshot_monthly`) y los
  presupuestos de consultas siguen verdes.
"""

import re
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, landscape

from apps.core import pdf as corepdf
from apps.registry.models import CostCenter
from apps.registry.report_views import AIRCRAFT_COL_WIDTHS, OPERATOR_COL_WIDTHS
from apps.registry.selectors import cost_center_universe, universe_sentence
from apps.registry.test_lv145_catastro_views import reader, world  # noqa: F401


def _size(pdf_bytes):
    box = PdfReader(BytesIO(pdf_bytes)).pages[0].mediabox
    return round(float(box.width), 1), round(float(box.height), 1)


def _a4(landscape_=False):
    width, height = landscape(A4) if landscape_ else A4
    return round(width, 1), round(height, 1)


@pytest.fixture
def admin(db):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


@pytest.mark.django_db
class TestOnePaper:
    def test_the_compliance_pdf_is_a4_portrait(self, admin):
        response = admin.get(reverse("compliance-report-pdf"))

        assert _size(response.content) == _a4()

    def test_the_roster_pdf_is_a4_landscape(self, reader):  # noqa: F811
        response = reader.get(reverse("registry-roster-pdf"))

        assert _size(response.content) == _a4(landscape_=True)

    def test_a_pdf_with_no_size_given_is_a4(self):
        from reportlab.platypus import Paragraph

        head = corepdf.Letterhead(title="x")
        data = corepdf.build_pdf(
            [Paragraph("x", corepdf.executive_stylesheet()["Normal"])], head
        )

        assert _size(data) == _a4()

    def test_the_roster_tables_fill_the_a4_landscape_frame(self):
        frame = landscape(A4)[0] - 2 * corepdf.SIDE_MARGIN

        assert sum(AIRCRAFT_COL_WIDTHS) == pytest.approx(frame, abs=0.5)
        assert sum(OPERATOR_COL_WIDTHS) == pytest.approx(frame, abs=0.5)

    def test_no_report_module_asks_reportlab_for_letter(self):
        """Carta era herencia de reportlab, no una decisión: si alguien la vuelve
        a importar, los tres papeles vuelven."""
        offenders = []
        for path in (Path(settings.BASE_DIR) / "apps").rglob("*.py"):
            if path.name.startswith("test") or "airspace" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"pagesizes import[^\n]*\bletter\b", text):
                offenders.append(str(path.relative_to(settings.BASE_DIR)))
        assert not offenders, f"papel Carta en: {offenders}"


class TestTheRosterWearsThePaperHeader:
    def test_it_has_the_same_paper_head_and_foot_as_the_compliance_report(
        self,
        reader,  # noqa: F811
        settings,
    ):
        settings.REPORT_CONTACT_EMAIL = "contacto@example.test"

        content = reader.get(reverse("registry-roster")).content.decode()

        assert 'class="id-print-head"' in content
        assert 'class="id-print-foot"' in content
        assert "contacto@example.test" in content
        assert 'class="page-header d-print-none"' in content
        head = re.search(
            r'<div class="id-print-head".*?</div>', content, re.DOTALL
        ).group(0)
        assert "Catastro de flota y personal" in head
        assert timezone.localdate().isoformat() in head  # la fecha de corte

    def test_the_screen_header_is_not_printed(self, reader):  # noqa: F811
        content = reader.get(reverse("registry-roster")).content.decode()

        screen = re.search(r'<div class="page-header[^"]*"', content).group(0)
        assert "d-print-none" in screen


@pytest.mark.django_db
class TestTheUniverseIsWritten:
    @pytest.fixture
    def centres(self):
        CostCenter.objects.create(code="A1", name="Opera", operates_flights=True)
        CostCenter.objects.create(code="A2", name="Sin vuelo", operates_flights=False)
        CostCenter.objects.create(
            code="A3",
            name="Cerrada",
            operates_flights=True,
            contract_status=CostCenter.CONTRACT_CLOSED,
        )
        CostCenter.objects.create(
            code="A4", name="Archivada", operates_flights=True, is_active=False
        )

    def test_the_numbers_follow_the_one_definition_of_operating(self, centres):
        """Activas: A1, A2, A3. Con operación (LV-266): activa + vuela + contrato
        abierto, o sea sólo A1."""
        assert cost_center_universe() == {"active": 3, "operating": 1}

    def test_the_sentence_is_translated(self):
        with translation.override("es"):
            assert (
                universe_sentence({"active": 3, "operating": 1})
                == "Faenas activas: 3 · con operación: 1"
            )
        assert gettext("as of %(date)s") % {"date": "26-10-2026"} == "al 26-10-2026"

    def test_the_compliance_report_says_it_under_the_cost_centre_table(
        self, admin, centres
    ):
        content = admin.get(reverse("compliance-report")).content.decode()

        assert re.search(
            r"data-universe>Faenas activas: 3 · con operación: 1</p>", content
        )

    def test_the_roster_says_it_under_each_table(self, reader, centres):  # noqa: F811
        content = reader.get(reverse("registry-roster")).content.decode()

        assert content.count("data-universe>Faenas activas: ") == 2

    def test_a_user_only_sees_the_universe_of_their_tenant(self, centres):
        from apps.core.models import OperationalTenant
        from apps.core.testing import login_as

        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        CostCenter.objects.filter(code="A1").update(tenant=other)
        member = login_as("view_aircraft", "view_operator").user

        # Sin pertenencia, cae al tenant por defecto: A1 (de otro tenant) no entra.
        scoped = cost_center_universe(member)

        assert scoped["operating"] == 0
        assert cost_center_universe()["operating"] == 1


@pytest.mark.django_db
class TestEveryPermitFigureSaysItsDate:
    def test_both_permit_cards_carry_the_as_of_date(self, admin):
        from datetime import timedelta

        from apps.operations.models import FlightPermission

        centre = CostCenter.objects.create(
            code="P1", name="Faena", operates_flights=True
        )
        today = timezone.localdate()
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=today - timedelta(days=60),
            valid_until=today - timedelta(days=1),
        )

        content = admin.get(reverse("compliance-report")).content.decode()

        expected = f"al {today:%d-%m-%Y}"
        assert content.count(f"data-as-of>{expected}</small>") == 2

    def test_the_figures_themselves_did_not_change(self, admin):
        from apps.compliance.kpis import permit_counts

        response = admin.get(reverse("compliance-report"))

        assert response.context["report"]["permits"] == permit_counts(
            timezone.localdate(), None
        )
