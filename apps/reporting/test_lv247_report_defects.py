"""LV-247: cuatro defectos del informe mensual, encontrados al revisarlo entero.

Sale del plan de mejora del 2026-09-23 (Fase 1a). Van antes que cualquier mejora
porque tres de los cuatro afectan lo que queda en el papel firmado.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from django.conf import settings

from apps.reporting.models import ReportRun

# Un mes cerrado: `freeze` se niega a congelar un período en curso (`LV-233`).
PERIOD = date(2026, 8, 1)


class TestARevisionKeepsTheWholeNarrative:
    @pytest.mark.django_db
    def test_forcing_a_revision_carries_the_actions(self, db):
        """⚠️ **Emitir una revisión borraba las acciones.** El docstring de
        `freeze` promete que "la narrativa viaja", y la narrativa son tres bloques:
        se copiaban hallazgos y observación, y las acciones —que llegaron después,
        con `LV-235`— se quedaban atrás. Corregir una cifra perdía en silencio lo
        escrito, justo cuando alguien está corrigiendo y menos lo va a notar."""
        first, _created = ReportRun.freeze(PERIOD, generated_by="lv247")
        first.actions = [
            {"action": "Renovar el permiso de CC684", "owner": "ADC", "due": ""}
        ]
        first.findings = [{"severity": "high", "title": "Faenas sin permiso"}]
        first.period_note = "Vigencias no uniformes."
        first.save()

        second, created = ReportRun.freeze(PERIOD, generated_by="lv247", force=True)

        assert created
        assert second.revision == first.revision + 1
        assert second.actions == first.actions
        # Y las otras dos siguen viajando: el arreglo no puede costar las que ya
        # funcionaban.
        assert second.findings == first.findings
        assert second.period_note == first.period_note


class TestTheExecutiveBriefSaysWhatItCounts:
    def test_the_heading_no_longer_promises_the_next_60_days(self):
        """Las filas de seguros y credenciales cuentan **vencidos**
        (`insurance_lapsed`, `credentials_lapsed`) bajo un título que decía
        "próximos 60 días": un 1 ahí se leía como "algo vence pronto" cuando ya
        venció."""
        template = (
            Path(settings.BASE_DIR) / "templates" / "reporting" / "executive_brief.html"
        ).read_text(encoding="utf-8")

        assert 'rpt-label">Vencimientos próximos 60 días' not in template
        assert 'rpt-label">Por vencer y por renovar' in template


class TestTheBriefSheetExists:
    def test_rpt_sheet_is_defined_in_the_report_stylesheet(self):
        """La plantilla usaba `rpt-sheet` y la clase no existía: la hoja salía sin
        ancho de A4, sin fondo y sin reglas de impresión. Mismo defecto que la
        `table-warning-subtle` del panel (`LV-246`), y el mismo guardián: una clase
        desconocida no falla, no pinta."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "report-a4.css").read_text(
            encoding="utf-8"
        )

        assert re.search(r"^\.rpt-sheet\s*\{", css, re.MULTILINE)

    def test_it_is_not_clipped_like_a_fixed_height_sheet(self):
        """`min-height` y no `height` + `overflow: hidden`: es una sola hoja cuyo
        contenido crece con las faenas, y recortar filas en silencio es el defecto
        que costó `pagination.py`."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "report-a4.css").read_text(
            encoding="utf-8"
        )
        # LV-259: hay dos bloques que abren con `.rpt-sheet {` — el de los tokens
        # del papel (compartido con `.rpt-doc`) y el de la maquetación. Se afirma
        # sobre el que declara el ancho de la hoja.
        blocks = re.findall(r"^\.rpt-sheet\s*\{(.*?)\}", css, re.MULTILINE | re.DOTALL)
        layout = next(block for block in blocks if "width:" in block)

        assert "min-height" in layout
        assert "overflow: hidden" not in layout
