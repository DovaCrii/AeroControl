"""LV-259: el contraste se calcula, y lo calcula el gate.

Pedido del usuario el 2026-09-25: *"el contraste no se visualiza bien en formato
oscuro"*. Se midieron 16 pantallas con los dos temas, calculando cada texto
contra su fondo efectivo, y salieron cuatro familias por debajo del mínimo:

- **El Dato Ejecutivo en oscuro, a 1,12 : 1**: su hoja usaba `var(--rpt-ink)`
  pero los tokens sólo existían dentro de `.rpt-doc`, así que el texto heredaba
  el color claro del tema y se pintaba sobre papel blanco.
- El rojo y el verde de Bootstrap en oscuro (3,66), el blanco sobre amarillo de
  las insignias (1,63) y la paleta del papel del informe (cian 2,9, gris 2,58).

Estos tests leen los archivos y hacen la cuenta — un ratio de contraste es
aritmética sobre dos colores, y leerlo de un navegador agrega una fuente de
error sin agregar información (`LV-207`).
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

STATIC = Path(settings.BASE_DIR) / "static" / "css"
REPORT_CSS = (STATIC / "report-a4.css").read_text(encoding="utf-8")
APP_CSS = (STATIC / "app.css").read_text(encoding="utf-8")

WHITE = "#ffffff"
AA_TEXT = 4.5


def _luminance(hex_colour):
    value = hex_colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground, background):
    high, low = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _token_block():
    """El bloque donde se declaran los tokens del papel, con su selector."""
    match = re.search(r"([^{}]*)\{([^}]*--rpt-navy:[^}]*)\}", REPORT_CSS)
    assert match, "no se encontró el bloque de tokens del informe"
    return match.group(1), match.group(2)


def _tokens():
    _selector, body = _token_block()
    return dict(re.findall(r"--(rpt-[\w-]+):\s*(#[0-9a-fA-F]{6})", body))


class TestTheTokensReachBothSheets:
    def test_the_executive_brief_sheet_gets_the_tokens(self):
        """El defecto que dejaba el Dato Ejecutivo ilegible en oscuro."""
        selector, _body = _token_block()

        assert ".rpt-sheet" in selector
        assert ".rpt-doc" in selector

    def test_every_token_used_is_declared(self):
        """Una variable sin declarar no es un error visible: el color se hereda
        del tema y en claro puede pasar por casualidad, que es exactamente cómo
        sobrevivió este defecto."""
        used = set(re.findall(r"var\(--(rpt-[\w-]+)\)", REPORT_CSS))

        assert used <= set(_tokens()), sorted(used - set(_tokens()))


class TestThePaperTextReadsOnPaper:
    @pytest.mark.parametrize(
        "token, background",
        [
            ("rpt-ink", WHITE),
            ("rpt-navy", WHITE),
            ("rpt-muted", WHITE),
            ("rpt-faint", WHITE),
            ("rpt-faint", "#f1f4f7"),  # la celda «No aplica» de la matriz
            ("rpt-cyan-ink", WHITE),
            ("rpt-cyan-ink", "#f4f7fa"),  # el mes de cada fase del plan
            ("rpt-amber-ink", WHITE),
            ("rpt-green-ink", "#dcefe6"),  # la celda «Exigible»
        ],
    )
    def test_text_tokens_reach_aa(self, token, background):
        ratio = contrast(_tokens()[token], background)

        assert ratio >= AA_TEXT, f"--{token} sobre {background}: {ratio:.2f}"

    def test_the_brand_cyan_is_not_used_as_text(self):
        """El cian de marca da 2,9 : 1: sirve para barras y bordes, no para letra."""
        assert contrast(_tokens()["rpt-cyan"], WHITE) < AA_TEXT
        text_rules = re.findall(r"(?<![-\w])color:\s*var\(--rpt-cyan\)", REPORT_CSS)

        assert not text_rules


class TestTheBootstrapColoursUsedLoose:
    def test_danger_and_success_are_lightened_in_the_dark_theme(self):
        for selector in (".text-danger", ".text-success", ".btn-outline-danger"):
            assert re.search(
                r'\[data-theme="dark"\]\s*' + re.escape(selector), APP_CSS
            ), selector

    def test_the_dark_danger_token_reads_on_the_dark_card(self):
        dark = re.search(
            r'\[data-theme="dark"\]\s*\{([^}]*--sev-critical-text[^}]*)\}', APP_CSS
        ).group(1)
        critical = re.search(r"--sev-critical-text:\s*(#[0-9a-fA-F]{6})", dark).group(1)

        assert contrast(critical, "#161f2d") >= AA_TEXT

    def test_yellow_and_cyan_badges_carry_dark_text(self):
        """Blanco sobre `#ffc107` es 1,63 : 1 en los dos temas."""
        rule = re.search(
            r"\.badge\.bg-warning,\s*\.badge\.bg-info\s*\{([^}]*)\}", APP_CSS
        )

        assert rule
        colour = re.search(r"color:\s*(#[0-9a-fA-F]{6})", rule.group(1)).group(1)
        assert contrast(colour, "#ffc107") >= AA_TEXT
        assert contrast(colour, "#0dcaf0") >= AA_TEXT

    def test_warning_text_is_not_bootstrap_yellow(self):
        assert re.search(
            r"\.text-warning\s*\{\s*color:\s*var\(--sev-warning-text\)", APP_CSS
        )
