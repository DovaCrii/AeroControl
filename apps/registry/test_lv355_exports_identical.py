"""LV-355 F1: el catastro exporta lo mismo antes y después de la tubería.

Los `golden/*.json` se generaron **con los escritores anteriores a
`apps/reporting/export.py`**; que sigan pasando prueba que unificar los escritores
no movió una celda, una negrita, el filtro anclado en la fila de encabezados ni un
ancho. Datos ficticios (las fixtures de `test_lv145_catastro_views`, que ya
llevan centinelas de fórmula en `model` y `operator_type`); reloj fijado.
"""

from datetime import datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import assert_golden, pin_now, workbook_grid

from .test_lv145_catastro_views import reader, world  # noqa: F401

GOLDEN = Path(__file__).resolve().parents[1] / "reporting" / "snapshots" / "exports"
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=dt_timezone.utc)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    pin_now(monkeypatch, NOW)


def test_xlsx(reader):  # noqa: F811
    grid = workbook_grid(reader.get(reverse("registry-roster-xlsx")).content)

    assert_golden(GOLDEN / "catastro_xlsx.json", grid)


def test_csv(reader):  # noqa: F811
    raw = reader.get(reverse("registry-roster-csv")).content

    assert_golden(
        GOLDEN / "catastro_csv.json",
        {
            "bom": raw.startswith(b"\xef\xbb\xbf"),
            "lines": raw.decode("utf-8-sig").split("\r\n"),
        },
    )


@pytest.mark.parametrize(
    "route,extension",
    [
        ("registry-roster-pdf", "pdf"),
        ("registry-roster-xlsx", "xlsx"),
        ("registry-roster-csv", "csv"),
    ],
)
def test_every_file_is_named_with_its_date(reader, route, extension):  # noqa: F811
    """S12: `stem_AAAA-MM-DD`, la fecha de corte del informe."""
    disposition = reader.get(reverse(route))["Content-Disposition"]

    assert disposition == (
        f'attachment; filename="aerocontrol-catastro_2026-10-26.{extension}"'
    )
