"""PR3 de la dirección visual técnica (`LV-451`): guardián de las ilustraciones `tk-*`.

Fija lo que no puede degradarse: que cada `tk-*.svg` sea un trazo técnico **heredado** (sin
colores propios dentro del dibujo, sin `var()`, `<style>`, `style=""`, texto ni imágenes
incrustadas), liviano, con `<symbol id="art">` y su `<use href="#art">` para verse suelto, y que
toda plantilla que lo dibuje lo haga con `#art` dentro de un `<svg aria-hidden="true">`.

`test_lv302_illustrations.py` sigue exigiendo `drone-scan.svg`, `permit-clipboard.svg` y
`route-map.svg`: aún hay plantillas con los doodles viejos (login, aeronaves, vuelos) y se
retiran en el PR de limpieza; por eso esa afirmación no cambia en este PR.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ILLUSTRATIONS = ROOT / "static" / "img" / "illustrations"
TEMPLATES = ROOT / "templates"

FORBIDDEN = re.compile(
    r"<style|\bstyle\s*=|var\(|<text|<image|<script|<foreignObject|\bon\w+\s*=|https?:",
    re.IGNORECASE,
)
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
TK_REFERENCE = re.compile(r"img/illustrations/(tk-[\w-]+\.svg)")


def _tk_svgs():
    return sorted(ILLUSTRATIONS.glob("tk-*.svg"))


def _without_root_tag(source: str) -> str:
    """El SVG sin su etiqueta raíz: ahí y sólo ahí viven los hex de respaldo."""
    return re.sub(r"<svg\b[^>]*>", "", source, count=1)


def test_the_first_batch_exists():
    names = {p.name for p in _tk_svgs()}
    assert {"tk-operator.svg", "tk-quad-top.svg"} <= names


@pytest.mark.parametrize("path", _tk_svgs(), ids=lambda p: p.name)
class TestEachTechnicalIllustration:
    def test_it_parses_and_has_the_art_symbol_and_its_use(self, path):
        source = path.read_text(encoding="utf-8")
        root = ET.fromstring(source)
        assert root.tag.endswith("svg")
        assert '<symbol id="art"' in source
        assert '<use href="#art"' in source

    def test_it_is_light(self, path):
        assert path.stat().st_size <= 6_000

    def test_it_carries_no_code_text_or_frozen_tone(self, path):
        body = _without_root_tag(path.read_text(encoding="utf-8"))
        assert not FORBIDDEN.search(body), path.name
        # Los hex de la raíz son el respaldo del tema claro; dentro del dibujo, ninguno.
        assert not HEX.search(body), path.name


class TestTheTemplatesDrawThemSafely:
    def test_the_shared_partial_draws_art_inside_an_aria_hidden_svg(self):
        html = (TEMPLATES / "generic" / "_empty_art.html").read_text(encoding="utf-8")
        match = re.search(r"<svg\b[^>]*>\s*<use href=\"\{\{ art_file \}\}#art\"", html)
        assert match, "el parcial debe dibujar `art_file` con `<use ...#art>`"
        assert 'aria-hidden="true"' in match.group(0)
        assert "tk-plate" in html

    def test_every_template_using_a_tk_file_hands_it_to_the_partial(self):
        users = {}
        for template in TEMPLATES.rglob("*.html"):
            text = template.read_text(encoding="utf-8")
            for name in TK_REFERENCE.findall(text):
                users.setdefault(template, []).append((name, text))
        assert users, "ninguna plantilla usa aún un tk-*.svg"
        for template, found in users.items():
            for name, text in found:
                assert (ILLUSTRATIONS / name).exists(), (template, name)
                assert "art_file=art_file" in text or "#art" in text, template

    def test_the_operator_lists_use_the_operator_emblem_and_not_the_old_doodles(self):
        for name in (
            "_operator_rows.html",
            "_operatorassignment_rows.html",
            "_qualification_rows.html",
        ):
            text = (TEMPLATES / "registry" / name).read_text(encoding="utf-8")
            assert "tk-operator.svg" in text, name
            assert "team.svg" not in text and "certificates.svg" not in text, name

    def test_the_generic_empty_list_uses_the_top_view_drone(self):
        text = (TEMPLATES / "generic" / "_table_body.html").read_text(encoding="utf-8")
        assert "tk-quad-top.svg" in text
        assert "drone-scan.svg" not in text
