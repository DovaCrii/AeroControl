"""UX-01: la severidad como token, en cinco niveles.

Del plan UX (`docs/ux-ui-plan.md` §6): la severidad se escribía con utilidades de
Bootstrap y **nada garantizaba que ámbar significara lo mismo en la tabla de
alertas, en el panel y en el informe**. En una app de cumplimiento aeronáutico eso
no es estética.

**Los valores no son nuevos**: son los de `LV-D10`, que ya los eligió y midió para
cumplir AA en los dos temas. Lo que cambia es que dejan de llamarse por su color
(`warning`, `info`) y pasan a llamarse por su significado. Inventar colores nuevos
habría tirado una medición hecha.

El contraste se **calcula** acá, no se lee de un navegador: es aritmética sobre dos
hex, el CSS los tiene, y el diagnóstico de `LV-207` demostró hoy que leerlo de un
navegador añade una fuente de error sin añadir información. Los helpers se
reutilizan de `test_lv207_one_colour_per_section.py`.
"""

import re
from pathlib import Path

import pytest

from apps.compliance.digest import BUCKET_BADGE_CSS, BUCKET_TEXT_CSS
from apps.core.test_lv207_one_colour_per_section import contrast

CSS = Path("static/css/app.css")
LEVELS = ("critical", "warning", "caution", "advisory", "nominal")
# WCAG AA para texto pequeño. Más exigente que el 3:1 de los iconos de `LV-207`
# porque acá el token pinta **texto** sobre su propio relleno.
TEXT_MIN = 4.5


def _tokens(dark=False):
    """`{nivel: {bg, border, text}}` leído del CSS, por tema.

    Se localiza por **orden de declaración** y no por el selector que lo envuelve:
    la primera aparición de `--sev-critical-bg` es la del tema claro y la segunda
    la del oscuro. La versión anterior de este helper buscaba
    `[data-theme="dark"] {` y leía el tema claro dos veces, porque ese selector
    aparece muchas veces antes en la hoja — lo delató
    `test_the_dark_theme_is_not_the_light_one`, que es exactamente para lo que
    servía.
    """
    css = CSS.read_text(encoding="utf-8")
    # Con los dos puntos: `--sev-critical-bg:` es una **declaración**, mientras
    # `var(--sev-critical-bg)` es un uso. Sin ese detalle salían tres anclas y no
    # dos, y el propio assert de abajo lo delató.
    anchors = [m.start() for m in re.finditer(r"--sev-critical-bg:", css)]
    assert len(anchors) == 2, (
        f"se esperaban dos declaraciones de --sev-critical-bg (claro y oscuro), "
        f"hay {len(anchors)}"
    )
    start = anchors[1] if dark else anchors[0]
    end = css.index("}", start)
    fragment = css[start:end]
    found = {}
    for level in LEVELS:
        for part in ("bg", "border", "text"):
            match = re.search(rf"--sev-{level}-{part}:\s*(#[0-9a-f]{{6}})", fragment)
            if match:
                found.setdefault(level, {})[part] = match.group(1)
    return found


class TestTheFiveLevelsExistInBothThemes:
    @pytest.mark.parametrize("dark", [False, True])
    def test_every_level_declares_its_three_parts(self, dark):
        tokens = _tokens(dark=dark)

        assert set(tokens) == set(LEVELS)
        for level, parts in tokens.items():
            assert set(parts) == {"bg", "border", "text"}, level

    @pytest.mark.parametrize("dark", [False, True])
    def test_the_text_clears_aa_on_its_own_fill(self, dark):
        """El criterio del plan UX, comprobado por cálculo."""
        for level, parts in _tokens(dark=dark).items():
            ratio = contrast(parts["text"], parts["bg"])
            assert ratio >= TEXT_MIN, (
                f"sev-{level}: {parts['text']} sobre {parts['bg']} da {ratio}"
            )

    def test_the_dark_theme_is_not_the_light_one(self):
        """Un tema oscuro que repite los rellenos claros no es un tema oscuro."""
        light, dark = _tokens(), _tokens(dark=True)

        for level in LEVELS:
            assert light[level]["bg"] != dark[level]["bg"], level


class TestTheScaleIsOrdered:
    def test_critical_and_nominal_are_not_the_same_colour(self):
        """Los dos extremos tienen que distinguirse sin leer el texto."""
        tokens = _tokens()

        assert tokens["critical"]["text"] != tokens["nominal"]["text"]

    def test_warning_and_caution_share_family_on_purpose(self):
        """**Deliberado, no un descuido.**

        Los dos son ámbar porque los dos dicen "esta quincena"; se separan por el
        peso del texto en la fila. Dos ámbares a distancia corta serían dos avisos
        que nadie distingue — hoy se midió (`LV-217`) que dos fondos suaves
        separados por poco son indistinguibles, así que no se finge una diferencia
        que el ojo no ve.
        """
        tokens = _tokens()

        assert tokens["warning"]["bg"] == tokens["caution"]["bg"]

    def test_the_weight_is_what_separates_them(self):
        """Y si comparten color, el peso tiene que hacer el trabajo."""
        css = CSS.read_text(encoding="utf-8")
        warning = re.search(r"\.sev-text-warning\s*\{([^}]+)\}", css).group(1)
        caution = re.search(r"\.sev-text-caution\s*\{([^}]+)\}", css).group(1)

        assert "font-weight" in warning
        assert "font-weight" in caution
        assert warning != caution


class TestTheUrgencyScaleUsesTheTokens:
    def test_both_representations_map_to_the_five_levels(self):
        pastilla = {css.removeprefix("sev-") for css in BUCKET_BADGE_CSS.values()}
        texto = {css.removeprefix("sev-text-") for css in BUCKET_TEXT_CSS.values()}

        assert pastilla == set(LEVELS)
        assert texto == set(LEVELS)

    def test_no_bootstrap_utility_is_left_in_the_scale(self):
        """El punto de la fila: la escala deja de nombrar utilidades ajenas.

        `bg-warning-subtle` puede aparecer en cualquier plantilla queriendo decir
        cualquier cosa; `sev-caution` no.
        """
        todas = list(BUCKET_BADGE_CSS.values()) + list(BUCKET_TEXT_CSS.values())

        for css in todas:
            assert "bg-" not in css, css
            assert "text-danger" not in css, css
            assert "-emphasis" not in css, css

    def test_the_classes_exist_in_the_stylesheet(self):
        """Una clase sin regla deja la pastilla sin color y nadie lo nota."""
        css = CSS.read_text(encoding="utf-8")

        for level in LEVELS:
            assert f".badge.sev-{level}" in css
            assert f".sev-text-{level}" in css

    def test_the_new_classes_need_no_important(self):
        """**La razón por la que esto reduce deuda en vez de agregarla.**

        Las quince reglas de `LV-D10` llevan `!important` porque pelean contra las
        utilidades de Bootstrap, que vienen con `!important` de fábrica. Una clase
        propia no compite con nadie, así que no lo necesita — y si alguien se lo
        agrega, es señal de que volvió a colgar la severidad de una utilidad ajena.
        """
        css = CSS.read_text(encoding="utf-8")

        for level in LEVELS:
            regla = re.search(rf"\.badge\.sev-{level}\s*\{{([^}}]+)\}}", css).group(1)
            assert "!important" not in regla, level
