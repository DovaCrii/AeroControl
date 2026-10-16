"""LV-321: plano técnico de la cabecera del panel y de la portada (OLA F, PR 1).

Garantías: los dibujos son SVG en línea y livianos, sin recursos externos; la cabecera del panel no
lleva movimiento continuo (sólo la portada, bajo `[data-ambient]`); nada parpadea (`steps(` en bucle);
y el script que pausa el movimiento ambiental no hace llamadas de red.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = (ROOT / "templates/dashboard/index.html").read_text(encoding="utf-8")
LOGIN = (ROOT / "templates/registration/login.html").read_text(encoding="utf-8")
BASE = (ROOT / "templates/base.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static/js/ambient-motion.js").read_text(encoding="utf-8")
AIRCRAFT = sorted((ROOT / "static/img/aircraft").glob("*.svg"))


def _svg(html, css_class):
    match = re.search(rf'<svg class="{css_class}".*?</svg>', html, re.S)
    assert match, css_class
    return match.group(0)


def _motion_block():
    marker = "@media (prefers-reduced-motion: no-preference) {"
    start = CSS.index(marker)
    depth = 0
    for index in range(start + len(marker) - 1, len(CSS)):
        depth += {"{": 1, "}": -1}.get(CSS[index], 0)
        if depth == 0:
            return CSS[start:index]
    raise AssertionError("bloque sin cerrar")


class TestTheDrawings:
    def test_inline_svg_within_the_size_cap(self):
        assert len(_svg(DASHBOARD, "hero-sky").encode()) <= 12 * 1024
        assert len(_svg(LOGIN, "showcase-route").encode()) <= 15 * 1024

    def test_no_external_resources(self):
        for svg in (_svg(DASHBOARD, "hero-sky"), _svg(LOGIN, "showcase-route")):
            assert not re.search(r"href=|<image|<use|<script|https?:|on\w+=", svg, re.I)

    def test_both_show_the_quadcopter_with_spinning_props(self):
        for svg in (_svg(DASHBOARD, "hero-sky"), _svg(LOGIN, "showcase-route")):
            assert svg.count("bp-blades") == 4

    def test_the_panel_drawing_has_dimension_marks_and_a_fixed_wing(self):
        svg = _svg(DASHBOARD, "hero-sky")
        assert "350 mm" in svg and "bp-wing" in svg and svg.count("route-wp") == 1

    def test_the_cover_drone_flies_the_route_with_a_side_view(self):
        svg = _svg(LOGIN, "showcase-route")
        assert "drone-fly" in svg and "bp-side" in svg and "drone-rotor" not in svg


class TestAmbientMotion:
    def test_only_the_cover_loops_and_it_is_marked_ambient(self):
        assert re.search(r'class="login-showcase"[^>]*\bdata-ambient\b', LOGIN)
        assert "data-ambient" not in DASHBOARD
        assert "ambient-motion.js" in LOGIN and "ambient-motion.js" in BASE
        for page in (LOGIN, BASE):
            assert re.search(r"ambient-motion\.js[^>]*\bdefer\b", page)

    def test_infinite_lives_only_under_data_ambient_and_can_be_paused(self):
        for line in CSS.splitlines():
            if "infinite" in line and "animation" in line:
                assert "[data-ambient]" in line, line
        assert re.search(
            r"\[data-ambient\]\.is-paused \*\s*\{\s*animation-play-state:\s*paused", CSS
        )

    def test_nothing_blinks(self):
        """Ni `steps(` en la hoja de estilos ni en los dibujos por serie: el LED parpadeante se fue."""
        assert "steps(" not in CSS
        for path in AIRCRAFT:
            text = path.read_text(encoding="utf-8")
            assert "steps(" not in text and "blink" not in text, path.name

    def test_continuous_cycles_are_slow(self):
        for line in _motion_block().splitlines():
            if "[data-ambient]" in line and "infinite" in line:
                seconds = float(re.search(r"\s([\d.]+)s\s", line).group(1))
                assert seconds >= 6, line

    def test_the_f2_anchor_sits_inside_the_motion_block(self):
        assert _motion_block().count("/* F2: entradas */") == 1
        assert CSS.count("/* F2: entradas */") == 1


class TestTheScript:
    def test_it_watches_visibility_and_motion_preference(self):
        for needle in (
            "IntersectionObserver",
            "visibilitychange",
            "prefers-reduced-motion: reduce",
            "is-paused",
        ):
            assert needle in SCRIPT

    def test_it_makes_no_network_calls(self):
        assert not re.search(
            r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket|EventSource|import\(|https?:",
            SCRIPT,
        )
