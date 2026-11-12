"""LV-436: la pantalla de análisis se veía gris y apagada en el tema oscuro.

Los rótulos de las tarjetas pasan al color primario, los valores al texto principal, el relato del
vuelo va destacado, las notas usan el texto secundario (no el apagado) y los gráficos van en
tarjetas de dos columnas con ejes y etiquetas más legibles.
"""

# ruff: noqa: F811 - las fixtures se importan de otras pruebas
import re
from pathlib import Path

import pytest

from .test_lv427_flight_log_analysis import centre, isolated_storage  # noqa: F401
from .test_lv429_dji_adapter import fake  # noqa: F401
from .test_lv431_flight_logs_section import drone  # noqa: F401
from .test_lv435_location_and_ui import _page, inside  # noqa: F401

CSS = (
    Path(__file__).resolve().parents[2] / "static/css/flight-analysis.css"
).read_text(encoding="utf-8")


def _rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, selector
    return match.group(1)


def test_the_narrative_is_highlighted(inside):
    html = _page(inside)

    assert 'id="fa-narrative" class="fa-narrative"' in html
    assert "var(--ac-primary-soft" in _rule(".fa-narrative")


def test_the_charts_sit_in_a_grid_of_cards(inside):
    html = _page(inside)

    grid = html.split('class="fa-charts"', 1)[1].split("</section>", 1)[0]
    assert grid.count('class="fa-figure"') == html.count('class="fa-figure"') > 0
    assert "grid-template-columns" in _rule(".fa-charts")


def test_labels_and_values_are_not_the_dimmed_grey():
    assert "var(--ac-primary" in _rule(".fa-facts dt")
    assert "var(--ac-text," in _rule(".fa-facts dd")
    for selector in (".fa-facts dt", ".fa-note", ".fa-sub"):
        assert "--bs-secondary-color" not in _rule(selector), selector
    assert "var(--ac-text-secondary" in _rule(".fa-page .text-muted")


def test_the_chart_text_is_readable():
    assert "font-size: 12px" in _rule(".fa-chart .fa-tick, .fa-chart .fa-label")
    assert "opacity: .6" not in _rule(".fa-chart .fa-axis")


@pytest.fixture(autouse=True)
def _db(db):
    return db
