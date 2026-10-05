"""LV-263: descargar el informe en PDF.

Pedido del usuario el 2026-10-05: *"necesito poder descargar el informe, aún no
puedo hacerlo"*. La pantalla no tenía ningún botón, y al imprimir a mano el PDF
salía con **siete** páginas para un informe de cinco — medido con un navegador
sin cabeza (`--print-to-pdf`):

- la primera, casi vacía: el encabezado de la pantalla empujaba la portada;
- la última, sólo el sello «Impreso desde AeroControl» de `base.html`;
- y el Dato Ejecutivo en dos: su regla de impresión `min-height: 0` perdía por
  orden contra la de pantalla, y 1123 px no caben en una A4 de 1122,5.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

CSS = Path(settings.BASE_DIR) / "static" / "css"
JS = Path(settings.BASE_DIR) / "static" / "js" / "app.js"


def _print_block(css):
    """El cuerpo del bloque `@media print` de `report-a4.css`."""
    start = css.index("@media print {")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i + 1 : j]
    raise AssertionError("bloque @media print sin cerrar")


@pytest.mark.django_db
class TestTheButtonIsThere:
    @pytest.fixture
    def report(self, client, admin_user):
        client.force_login(admin_user)
        return client.get(reverse("monthly-report"), {"period": "2026-09"})

    def test_the_report_has_a_download_button_named_after_its_code(self, report):
        body = report.content.decode()
        code = report.context["payload"]["meta"]["code"]
        button = re.search(r"<button[^>]*data-print[^>]*>(.*?)</button>", body, re.S)
        assert button, "sin botón de descarga"
        assert f'data-print-title="{code}"' in button.group(0)
        with translation.override("es"):
            assert button.group(1).strip() == gettext("Download PDF")

    def test_the_brief_has_a_download_button(self, client, admin_user):
        client.force_login(admin_user)
        body = client.get(
            reverse("monthly-report-brief"), {"period": "2026-09"}
        ).content.decode()
        assert re.search(r"<button[^>]*data-print[^>]*>", body)

    def test_the_screen_header_is_not_printed(self, report):
        """Impreso, el encabezado ocupaba la primera página entera."""
        body = report.content.decode()
        header = re.search(r'<div class="page-header[^"]*"', body).group(0)
        assert "d-print-none" in header


class TestThePrintRules:
    def test_the_print_stamp_does_not_add_a_page(self):
        block = _print_block((CSS / "report-a4.css").read_text(encoding="utf-8"))
        # `html body` delante: más específico que el `.print-stamp { display:
        # block !important }` de app.css, para no depender del orden de las hojas.
        assert re.search(
            r"html body \.print-stamp \{\s*display: none !important;\s*\}", block
        )

    def test_the_brief_sheet_loses_its_screen_height_on_paper(self):
        """La regla de pantalla va después: sin el `html` delante, gana ella."""
        css = (CSS / "report-a4.css").read_text(encoding="utf-8")
        block = _print_block(css)
        assert re.search(r"html \.rpt-sheet \{[^}]*min-height: 0", block)
        screen = css.index("min-height: 1123px", css.index("@media print {"))
        assert screen > css.index("@media print {"), "la premisa cambió: revisar"

    def test_the_button_opens_the_print_dialog(self):
        js = JS.read_text(encoding="utf-8")
        handler = js[js.index("closest('[data-print]')") :]
        assert "window.print()" in handler[:800]
        assert "afterprint" in handler[:800]
