"""LV-355 F1: el Reporte de vigencia exporta lo mismo antes y después de la tubería.

Los `golden/*.json` de esta carpeta se generaron **con los escritores anteriores a
`apps/reporting/export.py`** (cuatro copias de XLSX, CSV con BOM a mano): que
sigan pasando prueba que unificar los escritores no movió una celda, una negrita,
un filtro ni un ancho. Datos ficticios; el reloj queda fijado en 2026-10-26.

El centinela `=SENTINEL…` está en el nombre de la faena, que sale en las tres
salidas: si la neutralización de fórmulas se pierde en cualquiera, se ve.
"""

from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.core.testing import assert_golden, docx_grid, pin_now, workbook_grid
from apps.registry.models import Aircraft, CostCenter

from .models import Alert, AlertRule, Document, DocumentType
from .report_views import build_report_workbook_bytes
from .reports import build_compliance_report

GOLDEN = Path(__file__).resolve().parents[1] / "reporting" / "snapshots" / "exports"
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=dt_timezone.utc)
SENTINEL = "=SENTINEL(1+1)"


@pytest.fixture
def world(db, monkeypatch):
    pin_now(monkeypatch, NOW)
    centre = CostCenter.objects.create(code="FAENA-01", name=SENTINEL)
    other = CostCenter.objects.create(code="FAENA-02", name="Faena Sur")
    aircraft = Aircraft.objects.create(
        registration="RPA-901",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=centre,
    )
    doc_type = DocumentType.objects.create(code="SEG", name="Seguro")
    content_type = ContentType.objects.get_for_model(Aircraft)
    for title, expiry in [
        ("vencido", date(2026, 10, 21)),
        ("en 3 dias", date(2026, 10, 29)),
        ("en 10 dias", date(2026, 11, 5)),
        ("en 25 dias", date(2026, 11, 20)),
        ("vigente", date(2027, 3, 1)),
        ("sin fecha", None),
    ]:
        Document.objects.create(
            title=title,
            doc_type=doc_type,
            content_type=content_type,
            object_id=aircraft.pk,
            file_path=f"seg/{title}.pdf",
            issue_date=date(2026, 1, 1),
            expiry_date=expiry,
        )
    rule = AlertRule.objects.create(
        name="Documentos por vencer",
        entity_type="compliance.document",
        field_to_watch="expiry_date",
    )
    Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Document),
        object_id=Document.objects.get(title="en 3 dias").pk,
        message="aviso ficticio",
    )
    return {"centre": centre, "other": other}


@pytest.fixture
def admin(world):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


def _csv(response):
    raw = response.content
    return {
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "lines": raw.decode("utf-8-sig").split("\r\n"),
    }


@pytest.mark.django_db
class TestTheComplianceExportsAreUnchanged:
    def test_xlsx(self, admin):
        grid = workbook_grid(admin.get(reverse("compliance-report-xlsx")).content)

        assert_golden(GOLDEN / "compliance_xlsx.json", grid)

    def test_csv(self, admin):
        assert_golden(
            GOLDEN / "compliance_csv.json",
            _csv(admin.get(reverse("compliance-report-csv"))),
        )

    def test_docx(self, admin):
        grid = docx_grid(admin.get(reverse("compliance-report-docx")).content)

        assert_golden(GOLDEN / "compliance_docx.json", grid)

    def test_the_workbook_attached_to_the_email(self, world):
        grid = workbook_grid(build_report_workbook_bytes(build_compliance_report()))

        assert_golden(GOLDEN / "compliance_email_xlsx.json", grid)

    def test_a_filtered_csv_keeps_only_that_cost_centre(self, admin, world):
        response = admin.get(
            reverse("compliance-report-csv"), {"cost_center": str(world["other"].pk)}
        )

        assert_golden(GOLDEN / "compliance_csv_filtered.json", _csv(response))


@pytest.mark.django_db
class TestEveryFileIsNamedWithItsDate:
    """S12: `stem_AAAA-MM-DD` en las cuatro salidas y en el adjunto del correo."""

    @pytest.mark.parametrize(
        "route,extension",
        [
            ("compliance-report-csv", "csv"),
            ("compliance-report-xlsx", "xlsx"),
            ("compliance-report-docx", "docx"),
            ("compliance-report-pdf", "pdf"),
        ],
    )
    def test_the_download_carries_the_report_date(self, admin, route, extension):
        disposition = admin.get(reverse(route))["Content-Disposition"]

        assert disposition == (
            f'attachment; filename="aerocontrol-cumplimiento_2026-10-26.{extension}"'
        )

    def test_the_email_attachment_follows_the_same_pattern(self, world, settings):
        from django.core import mail
        from django.core.management import call_command

        settings.MAILERS = {
            "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
        }
        call_command("send_executive_report", "--period", "week", "--to", "a@test.com")

        assert mail.outbox[0].attachments[0][0] == (
            "aerocontrol-cumplimiento_2026-10-26.xlsx"
        )

    def test_the_file_the_command_writes_follows_it_too(self, world, tmp_path):
        from django.core.management import call_command

        target = tmp_path.joinpath("salida")
        call_command("compliance_report", "--output", str(target))

        assert [p.name for p in target.iterdir()] == [
            "aerocontrol-cumplimiento_2026-10-26.xlsx"
        ]

    def test_the_email_workbook_is_the_summary_sheet_without_the_total(self, admin):
        """Lo único que cambió del adjunto: ahora se autoajusta como la descarga
        (antes salía con el ancho por defecto). Las filas son las mismas."""
        download = workbook_grid(admin.get(reverse("compliance-report-xlsx")).content)
        email = workbook_grid(build_report_workbook_bytes(build_compliance_report()))

        summary = download["sheets"]["Resumen"]["rows"]
        assert email["order"] == ["Resumen"]
        assert email["sheets"]["Resumen"]["rows"] == summary[:-1]  # sin la fila TOTAL
