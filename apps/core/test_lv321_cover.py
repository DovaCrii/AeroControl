"""LV-321 (pedido del usuario): portada con topografía, rumbo, waypoints numerados y telemetría.

Todo es decoración (`aria-hidden`); lo que se vigila es que no le robe lectura al titular y a los
tres puntos, que el movimiento sea sólo ambiental y que el nombre no se repita en pantalla ancha.
"""

import re
from pathlib import Path

from apps.core.test_lv321_ambient import _motion_block, _svg

ROOT = Path(__file__).resolve().parents[2]
LOGIN = (ROOT / "templates/registration/login.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")


def _luminance(rgb):
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        for c in (v / 255 for v in rgb)
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _blend(top, bottom, share):
    return tuple(round(t * share + b * (1 - share)) for t, b in zip(top, bottom))


def _opacity(selector):
    block = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert block, selector
    return float(re.search(r"opacity:\s*([\d.]+)", block.group(1)).group(1))


def test_it_carries_contours_compass_numbered_waypoints_and_telemetry():
    svg = _svg(LOGIN, "showcase-route")
    assert svg.count('class="topo') >= 12 and "topo-label" in svg
    assert "RUMBO" in svg and "ALT 120 m" in svg and "BAT 87 %" in svg
    for number in range(1, 6):
        assert f"WP-0{number}" in svg
    assert svg.count("wp-ring") == 5
    assert "route-trail" in svg and "radar-sweep" in svg
    assert '<aside class="login-showcase" aria-hidden="true"' in LOGIN


def test_static_layers_under_the_text_keep_the_copy_readable():
    """Peor caso: los puntos (#cdd9f3) sobre el tramo más claro del fondo (el halo turquesa) con
    las curvas de nivel encima a su opacidad máxima."""
    for selector in (".topo", ".topo--index", ".topo-label"):
        assert _opacity(selector) <= 0.2, selector
    halo = _blend((34, 211, 197), (13, 28, 58), 0.24)
    worst = _blend((159, 216, 245), halo, _opacity(".topo--index"))
    ratio = (_luminance((205, 217, 243)) + 0.05) / (_luminance(worst) + 0.05)
    assert ratio >= 4.5, ratio


def test_trail_waypoints_and_radar_move_only_when_ambient():
    block = _motion_block()
    for name in ("radar-sweep", "route-trail", "wp-ring"):
        assert re.search(rf"\[data-ambient\] \.{name} \{{ animation:", block), name


def test_the_wordmark_is_big_and_the_card_does_not_repeat_it():
    brand = re.search(r"\.showcase-brand \{([^}]*)\}", CSS).group(1)
    assert float(re.search(r"font-size:\s*([\d.]+)rem", brand).group(1)) >= 1.6
    assert 'width="60" height="60"><span>AeroControl</span>' in LOGIN
    assert re.search(
        r"@media \(min-width: 992px\) \{\s*\.login-title \{[^}]*clip-path", CSS
    )
    # Bajo 992 px el panel no existe y la tarjeta conserva el nombre.
    assert '<h1 class="login-title">AeroControl</h1>' in LOGIN
