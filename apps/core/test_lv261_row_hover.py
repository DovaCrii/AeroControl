"""LV-261: al pasar el mouse, una fila con barra de severidad se realza entera.

Reportado por el usuario con captura el 2026-09-25 en la tabla de faenas del
panel: al señalar una fila crítica, las celdas se volvían gris azulado y la
primera seguía roja. `.table-hover` de Bootstrap pinta el realce con una sombra
interior sobre `--bs-table-bg-state`, y la primera celda —que declara su propia
sombra para la barra del canto— la reemplazaba en vez de sumarla.

Verificado en el navegador pasando el mouse: con el arreglo, las siete celdas de
la fila reciben el mismo realce, y las demás filas no.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

CSS = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
    encoding="utf-8"
)


def _rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"no se encontró {selector}"
    return match.group(1)


@pytest.mark.parametrize(
    "selector",
    [
        "tr.row-critical > td:first-child",
        'tr[data-sev="critical"] > td:first-child',
        'tr[data-sev="warning"] > td:first-child',
        'tr[data-sev="caution"] > td:first-child',
        'tr[data-sev="advisory"] > td:first-child',
    ],
)
def test_the_edge_bar_keeps_the_hover_layer(selector):
    """La barra del canto se **suma** al realce de Bootstrap, no lo reemplaza."""
    assert "var(--bs-table-bg-state" in _rule(selector)


def test_a_critical_row_deepens_its_red_on_hover():
    """El realce de una fila crítica es rojo; el gris de Bootstrap tapaba la
    señal justo cuando alguien la estaba mirando."""
    rule = _rule(".table-hover > tbody > tr.row-critical:hover > *")

    assert "--bs-table-bg-state" in rule
    assert "--sev-critical" in rule
