"""LV-171: la hoja de campo de SIGO deja de ser once cajas iguales.

Pedido del usuario, con el mismo diagnóstico que `LV-163`: *"once cajas
idénticas en peso y color"*. Rótulo y valor se dibujaban con el mismo tamaño y
el mismo gris, y las once casillas con el mismo borde, así que el ojo no tenía
por dónde entrar.

**No es un problema de contraste y no se aclaró ningún gris.** `LV-165` ya midió
que la paleta cumple AA en los dos temas y dejó escrito que aclarar un gris que
ya cumple reduce los niveles distinguibles y deja la pantalla *más* plana. Lo que
faltaba era jerarquía y color, que es lo que este cambio agrega.

Las propiedades que estos tests sostienen:

- **El valor pesa más que su rótulo.** Es lo que se transcribe casilla por
  casilla en el formulario del Estado; el rótulo sólo dice cuál es cuál.
- **Los cuatro acentos existen en los dos temas.** Un acento definido sólo en
  claro deja el tramo sin distinguir justo en el tema que el usuario usa.
- **El color no es el único portador.** Cada tramo conserva su título escrito,
  así que quien no distinga esos tonos no pierde información (WCAG 1.4.1).
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
FIELD = Path(settings.BASE_DIR) / "templates" / "geo" / "_sigo_field.html"
SHEET = Path(settings.BASE_DIR) / "templates" / "geo" / "_sigo_sheet.html"

ACCENTS = ("area", "admin", "coords", "circle")


@pytest.fixture(scope="module")
def css():
    return CSS.read_text(encoding="utf-8")


def _rule(css, selector):
    match = re.search(
        r"(?<![\w.-])" + re.escape(selector) + r"\s*\{(.*?)\}", css, re.DOTALL
    )
    return match.group(1) if match else ""


def _size(css, selector):
    match = re.search(r"font-size:\s*([\d.]+)rem", _rule(css, selector))
    return float(match.group(1)) if match else None


def _weight(css, selector):
    match = re.search(r"font-weight:\s*(\d+)", _rule(css, selector))
    return int(match.group(1)) if match else None


def test_the_value_outweighs_its_label(css):
    """Lo que se transcribe manda; el rótulo sólo dice cuál casilla es cuál."""
    assert _size(css, ".sigo-field-value") > _size(css, ".sigo-field-label")
    assert _weight(css, ".sigo-field-value") >= _weight(css, ".sigo-field-label")


def test_an_empty_box_stays_quiet(css):
    """Un guion no es un dato: no tiene por qué pesar como uno."""
    empty = _rule(css, ".sigo-field-value.is-empty")

    assert "--ac-text-muted" in empty
    assert "font-weight: 400" in empty


def test_the_numbers_line_up_across_boxes(css):
    """Grados, minutos y segundos se leen en columna."""
    assert "font-variant-numeric: tabular-nums" in _rule(css, ".sigo-field-value")


@pytest.mark.parametrize("accent", ACCENTS)
def test_every_accent_exists_in_both_themes(css, accent):
    light = re.search(rf"\.sigo-section-{accent}\s*\{{\s*--sigo-accent", css)
    dark = re.search(
        rf'\[data-theme="dark"\] \.sigo-section-{accent}[^{{]*\{{\s*--sigo-accent', css
    )

    assert light, f"falta el acento claro de {accent}"
    assert dark, f"falta el acento oscuro de {accent}: LV-171"


def test_latitude_and_longitude_share_one_accent():
    """Son las dos mitades de una coordenada; separarlas por color mentiría."""
    markup = SHEET.read_text(encoding="utf-8")

    assert markup.count("sigo-section-coords") == 4  # dos títulos y dos filas


def test_colour_is_never_the_only_carrier():
    """WCAG 1.4.1: cada tramo conserva su título escrito."""
    markup = SHEET.read_text(encoding="utf-8")

    for accent in ("admin", "coords", "circle"):
        assert f'class="sigo-section-title sigo-section-{accent}"' in markup


def test_the_box_no_longer_paints_itself_with_flat_utilities():
    """El estilo pasa a una clase propia: es lo que permite la jerarquía."""
    markup = FIELD.read_text(encoding="utf-8")

    assert 'class="sigo-field h-100"' in markup
    assert "border rounded p-2" not in markup
