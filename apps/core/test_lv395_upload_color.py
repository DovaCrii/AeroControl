"""LV-395: subir lleva su propio color, el azul corporativo J.E.J. (`#1E418C`).

Pedido del usuario (2026-11-03): los botones de subir no se distinguían, porque
usaban el mismo turquesa que cualquier acción primaria. Dos guardianes:

- **contraste**: los tokens `--ac-upload*` se CALCULAN con `contrast.py` en los dos
  temas (no se leen de un navegador): el relleno con su texto, y el color como
  texto/borde sobre la superficie y el fondo;
- **cobertura**: toda plantilla con `type="file"` y todo botón o enlace rotulado
  «Upload…» usan `.btn-upload*`. Se descubren solos, así que una plantilla nueva
  que suba archivos y se olvide de la clase falla aquí y no en producción.
"""

import re

import pytest

from apps.core.test_lv367_visual_base import (
    CONTRAST,
    ROOT,
    _contrast,
    _resolve,
    _theme_tokens,
)

TEMPLATES = ROOT / "templates"
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")

# Plantilla -> por qué NO lleva `.btn-upload*`. Cada excepción se justifica.
FILE_INPUT_EXCEPTIONS = {
    "registry/costcenter_import.html": (
        "importa un CSV (alta masiva de faenas): no es subir un documento; su campo "
        "de archivo sí toma el color por el `::file-selector-button` global"
    ),
}

# Un botón o enlace con clase `btn` cuyo rótulo traducible empieza por «Upload».
UPLOAD_ACTION = re.compile(
    r'<(?:a|button)\b[^>]*\bclass="(?P<cls>[^"]*\bbtn\b[^"]*)"[^>]*>'
    r"(?P<label>[^<]*\{%\s*translate\s+\"Upload[^\"]*\"\s*%\})"
)


def _pages():
    return {
        str(path.relative_to(TEMPLATES)).replace("\\", "/"): path.read_text(
            encoding="utf-8"
        )
        for path in TEMPLATES.rglob("*.html")
    }


@pytest.mark.parametrize("theme", ["light", "dark"])
class TestTheTokensContrast:
    def _pair(self, theme, fg, bg):
        tokens = _theme_tokens(theme)
        return _contrast(
            _resolve(tokens[f"--{fg}"], tokens), _resolve(tokens[f"--{bg}"], tokens)
        )

    def test_the_label_on_the_fill_is_readable_at_aaa(self, theme):
        assert self._pair(theme, "ac-upload-ink", "ac-upload") >= 7
        assert self._pair(theme, "ac-upload-ink", "ac-upload-hover") >= 7

    def test_the_colour_as_text_or_border_clears_aaa_on_both_surfaces(self, theme):
        assert self._pair(theme, "ac-upload", "ac-surface") >= 7
        assert self._pair(theme, "ac-upload", "ac-bg") >= 7

    def test_the_hover_stays_readable_as_text_too(self, theme):
        assert self._pair(theme, "ac-upload-hover", "ac-surface") >= 7

    def test_body_text_reads_on_the_soft_tint(self, theme):
        assert self._pair(theme, "ac-text", "ac-upload-soft") >= 7


def test_the_corporate_blue_is_the_light_fill():
    assert _theme_tokens("light")["--ac-upload"].lower() == "#1e418c"
    assert _theme_tokens("dark")["--ac-upload"].lower() == "#8fb0f0"


def test_the_script_measures_the_two_themes_differently():
    """El script distingue claro de oscuro; si leyera uno solo, ambos ratios serían iguales."""
    assert _theme_tokens("light")["--ac-upload"] != _theme_tokens("dark")["--ac-upload"]
    assert CONTRAST.ratio  # el módulo se cargó


def test_the_classes_and_the_global_file_button_are_styled():
    for rule in (
        ".btn-upload ",
        ".btn-upload-outline ",
        'input[type="file"]::file-selector-button',
    ):
        assert rule in APP_CSS


def test_the_dark_modal_does_not_repaint_the_file_button_grey():
    """Había una regla sólo para modales oscuros que lo dejaba gris; con ella viva el color no es global."""
    assert ".modal .form-control::file-selector-button" not in APP_CSS


def test_every_upload_action_uses_the_upload_class():
    offenders = []
    found = 0
    for name, html in _pages().items():
        for match in UPLOAD_ACTION.finditer(html):
            found += 1
            if "btn-upload" not in match.group("cls"):
                offenders.append((name, match.group("label").strip()))
    assert found >= 10, "el descubrimiento dejó de encontrar acciones de subida"
    assert not offenders, offenders


def test_every_template_with_a_file_input_uses_the_upload_class():
    offenders = [
        name
        for name, html in _pages().items()
        if 'type="file"' in html
        and "btn-upload" not in html
        and name not in FILE_INPUT_EXCEPTIONS
    ]
    assert not offenders, offenders


def test_the_exceptions_still_exist_and_are_still_needed():
    pages = _pages()
    for name, reason in FILE_INPUT_EXCEPTIONS.items():
        assert reason
        assert name in pages and 'type="file"' in pages[name]
        assert "btn-upload" not in pages[name]
