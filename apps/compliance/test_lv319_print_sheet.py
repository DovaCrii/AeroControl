"""LV-319: ola D del rediseño — informes impresos, documentos y SIGO.

Dos cosas se fijan acá: la hoja impresa (`identity.css`, sección D) y los estados como `.id-chip`
(texto + color) en las pantallas de informe y de documentos. Los textos del papel salen de la
configuración (`REPORT_CONTACT_*`), nunca del código.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.registry.models import Aircraft

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")
START = "/* == D: informes, documentos y SIGO == */"
SECTION_D = CSS[CSS.index(START) : CSS.index("/* == E: pulido global == */")]
PRINT = SECTION_D[SECTION_D.index("@media print") :]


def _luminance(hex_colour):
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


class TestPrintStylesheet:
    def test_the_page_has_margins_and_an_11pt_body(self):
        assert re.search(r"@page\s*\{[^}]*size:\s*A4;[^}]*margin:\s*[1-9]", PRINT)
        assert re.search(r"html body\s*\{[^}]*font-size:\s*11pt", PRINT)

    def test_rows_never_split_and_headers_repeat(self):
        assert re.search(r"tr,[^{]*\{\s*break-inside:\s*avoid", PRINT)
        assert "display: table-header-group" in PRINT

    def test_print_is_always_light(self):
        """Sin modo oscuro en papel: los tokens del tema oscuro se redeclaran en claro."""
        assert "color-scheme: light" in PRINT
        # Esta capa no redefine `--ac-*`/`--sev-*` (lo vigila LV-302): fuerza propiedades.
        assert not re.search(r"--(ac|sev)-[a-z-]+\s*:", PRINT)
        dark = re.search(
            r'html\[data-theme="dark"\] body,[^{]*\.card,[^{]*\{([^}]*)\}', PRINT
        ).group(1)
        assert (
            _luminance(re.search(r"background:\s*(#[0-9a-f]{6})", dark).group(1)) > 0.9
        )
        assert _luminance(re.search(r"color:\s*(#[0-9a-f]{6})", dark).group(1)) < 0.1
        assert "!important" in dark

    def test_no_shadows_and_the_footer_repeats_on_every_sheet(self):
        assert re.search(r"\.card,[^{]*\{[^}]*box-shadow:\s*none", PRINT)
        assert re.search(r"\.id-print-foot\s*\{[^}]*position:\s*fixed", PRINT)

    def test_the_paper_header_and_footer_do_not_exist_on_screen(self):
        before_print = SECTION_D[: SECTION_D.index("@media print")]
        assert re.search(
            r"\.id-print-head,\s*\.id-print-foot\s*\{\s*display:\s*none", before_print
        )

    def test_sigo_copy_buttons_stay_on_screen_but_not_on_paper(self):
        assert re.search(r"\.copy-btn,[^{]*\{\s*display:\s*none\s*!important", PRINT)
        sheet = (ROOT / "templates" / "geo" / "_sigo_copy_button.html").read_text(
            encoding="utf-8"
        )
        assert 'class="btn btn-sm btn-outline-secondary copy-btn"' in sheet
        assert 'data-copy="{{ value }}"' in sheet

    def test_the_monthly_report_keeps_its_zero_margin_sheet(self):
        """`report-a4.css` carga después y fija `margin: 0`; la hoja A4 es la página."""
        a4 = (ROOT / "static" / "css" / "report-a4.css").read_text(encoding="utf-8")
        assert re.search(r"@page\s*\{\s*size:\s*A4;\s*margin:\s*0", a4)
        base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
        assert base.index("css/identity.css") < base.index("block extrahead")


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(
        registration="CC-L319", type="RPA", model="M3", manufacturer="DJI"
    )


def _document(aircraft, *, expiry):
    doc_type = DocumentType.objects.create(
        name="Póliza", code="policy", requires_expiry=False
    )
    return Document.objects.create(
        title="Póliza L319",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        issue_date=date.today() - timedelta(days=30),
        expiry_date=expiry,
        file_path="",
    )


@pytest.mark.django_db
class TestDocumentStates:
    def test_a_current_document_shows_a_text_chip(self, aircraft):
        document = _document(aircraft, expiry=date.today() + timedelta(days=200))
        page = login_as("view_document").get(
            reverse("document-detail", args=[document.pk])
        )
        content = page.content.decode()
        assert 'class="id-chip id-chip--ok">' in content
        assert "id-print-head" in content

    def test_an_expired_document_keeps_its_critical_badge(self, aircraft):
        document = _document(aircraft, expiry=date.today() - timedelta(days=5))
        page = login_as("view_document").get(
            reverse("document-detail", args=[document.pk])
        )
        content = page.content.decode()
        assert 'class="badge sev-critical">⚠ ' in content
        assert "id-chip--ok" not in content


@pytest.mark.django_db
class TestComplianceReportSheet:
    def test_the_footer_reads_the_contact_from_settings(self, settings):
        settings.REPORT_CONTACT_EMAIL = "contacto@example.test"
        page = login_as("view_document", "view_alert").get(reverse("compliance-report"))
        content = page.content.decode()
        assert 'class="id-print-foot"' in content
        assert "contacto@example.test" in content

    def test_the_screen_header_is_not_printed_but_the_paper_header_is(self):
        content = (
            login_as("view_document", "view_alert")
            .get(reverse("compliance-report"))
            .content.decode()
        )
        assert 'class="page-header d-print-none"' in content
        assert 'class="id-print-head"' in content
