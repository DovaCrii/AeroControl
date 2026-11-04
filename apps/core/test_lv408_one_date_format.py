"""`LV-408`: una sola forma de escribir una fecha en pantalla, `d-m-Y`.

Antes convivían `d-m-Y` (58), `Y-m-d` (51) y `d/m/Y` (5): la alerta mostraba
`2026-08-04` y la ficha del permiso `04-08-2026` en la misma sesión. Decisión del
usuario: `d-m-Y` en pantalla; `Y-m-d` sólo en exportaciones y en los atributos
que el navegador o una máquina leen (`<input type="date" value>`, `datetime=`).
"""

import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template

TEMPLATES = Path(settings.BASE_DIR) / "templates"
FORBIDDEN = re.compile(r"""date:\s*["'](Y-m-d|d/m/Y)""")

# Líneas donde el formato ISO es un contrato con el navegador, no un texto.
MACHINE_READ = re.compile(r"""type="date"|datetime=|value="\{\{""")


def test_screen_templates_show_dates_as_day_month_year():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if FORBIDDEN.search(line) and not MACHINE_READ.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{number}")

    assert not offenders, offenders


def test_the_guard_notices_a_violation():
    """El guardián no se queda verde por una expresión que no encuentra nada."""
    assert FORBIDDEN.search("{{ d|date:'Y-m-d' }}")
    assert FORBIDDEN.search('{{ d|date:"d/m/Y" }}')
    assert not FORBIDDEN.search('{{ d|date:"d-m-Y" }}')


def test_inputs_keep_the_iso_value_the_browser_requires():
    source = (TEMPLATES / "compliance" / "report.html").read_text(encoding="utf-8")

    assert "value=\"{{ report.period.start|date:'Y-m-d' }}\"" in source


def test_the_format_renders_day_month_year():
    import datetime

    html = Template('{{ d|date:"d-m-Y" }}').render(
        Context({"d": datetime.date(2026, 8, 4)})
    )

    assert html == "04-08-2026"
