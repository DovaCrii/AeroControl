"""LV-445: lo que `_tail_v2` predice para la sección 5 es lo que Edge imprime.

El cuerpo de cada hoja es `overflow: hidden`: una estimación corta recorta una fila
contra el pie sin avisar. Con un navegador sin cabeza (`--print-to-pdf`) y `pypdf` se
mide **dónde** cae lo último de cada hoja de la sección (la última faena de la tabla, la
última línea de 5.3 y el final de la observación) y se exige que quede sobre el pie.
Es la medición que fija `V2_MANUAL_*` en `pagination.py`; si se cambia el CSS o la
plantilla de la hoja, se vuelve a correr y se ajustan las constantes.
"""

import re

import pytest

from apps.reporting.builder import build
from apps.reporting.manual_case import CUTOFF, PERIOD, make_manual_case
from apps.reporting.test_lv378_summary_coverage_v2 import _edge, _html, _pdf_of
from apps.reporting.views import MonthlyReportView

pytestmark = pytest.mark.skipif(_edge() is None, reason="sin Edge/Chrome para imprimir")

#: El pie empieza a 1055,5 px de 1123: en puntos desde el borde de abajo.
FOOT_LIMIT_PT = (1123 - 1055.5) * 0.75
LONG_NOTE = " ".join(["Observación ficticia de largo completo."] * 30)[:1200]


def _lowest(reader, page, needle, exact=False):
    """La `y` (puntos desde abajo) más baja donde aparece `needle` en la página."""
    found = []

    def visit(text, cm, tm, _font, _size):
        if text and (text.strip() == needle if exact else needle in text):
            found.append(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])

    reader.pages[page - 1].extract_text(visitor_text=visit)
    return min(found) if found else None


@pytest.mark.parametrize(
    ("centres", "aircraft", "note"),
    [
        (3, 3, ""),
        (15, 20, ""),
        (15, 20, LONG_NOTE),
        (22, 20, ""),
        (24, 20, ""),
        (25, 20, ""),
        (40, 20, LONG_NOTE),
    ],
)
def test_the_manual_sheets_print_where_the_reparto_says(
    db, client, tmp_path, centres, aircraft, note
):
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    sites = make_manual_case(centres=centres, aircraft_count=aircraft)
    payload = build(PERIOD, cutoff=CUTOFF)[0]
    html = _html(client, payload, manual_note=note)
    sheets = MonthlyReportView._sheets(payload, "", note)
    reader = PdfReader(str(_pdf_of(html, tmp_path)))

    assert len(reader.pages) == sheets["total_pages"]
    manual = sheets["manual_sheets"]
    assert manual
    for sheet in manual:
        flat = " ".join(reader.pages[sheet["page"] - 1].extract_text().split())
        assert f"Página {sheet['page']} de {sheets['total_pages']}" in flat
        assert "Cumplimiento del Manual de Operaciones" in flat
        for row in sheet["rows"]:
            y = _lowest(reader, sheet["page"], row["code"], True)
            assert y is not None and y > FOOT_LIMIT_PT, (row["code"], y)
    last = manual[-1]["page"]
    print(f"\nMEDIDO {centres}x{aircraft} nota={len(note)}: hojas={len(manual)}")
    for needle in ("sólo área no poblada", "Observación ficticia", sites[-1].code):
        print("  ", needle, _lowest(reader, last, needle))
    assert _lowest(reader, last, "sólo área no poblada") > FOOT_LIMIT_PT
    if note:
        assert _lowest(reader, last, note[-20:]) > FOOT_LIMIT_PT
    first = manual[0]["page"]

    def px(y):
        return round(1123 - y / 0.75, 1)

    rows = manual[0]["rows"]
    print("  hojas con filas:", [len(sheet["rows"]) for sheet in manual])
    print("  primera fila px:", px(_lowest(reader, first, rows[0]["code"], True)))
    if len(rows) > 1:
        print(
            "  pitch px:",
            px(_lowest(reader, first, rows[1]["code"], True))
            - px(_lowest(reader, first, rows[0]["code"], True)),
        )
    print(
        "  ultima fila hoja 1 px:", px(_lowest(reader, first, rows[-1]["code"], True))
    )
    print(
        "  5.2 px:",
        px(_lowest(reader, last, "5.2 OTROS")),
        "5.3 px:",
        px(_lowest(reader, last, "5.3 QU")),
        "fin 5.3 px:",
        px(_lowest(reader, last, "sólo área no poblada")),
    )
    if note:
        print(
            "  Observación px:",
            px(_lowest(reader, last, "Observación")),
            "fin nota px:",
            px(_lowest(reader, last, note[-20:])),
        )
    if len(manual) > 1 and manual[-1]["rows"]:
        print(
            "  cont. primera fila px:",
            px(_lowest(reader, last, manual[-1]["rows"][0]["code"], True)),
        )
    assert re.search(r"5\.1 REG-016", reader.pages[first - 1].extract_text())
