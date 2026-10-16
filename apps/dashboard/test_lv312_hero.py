"""LV-312: cabecera del panel con fondo aeronáutico atenuado y chips con acción.

Cuatro garantías:

1. **El dibujo es sólo decoración**: sin recursos externos ni scripts, y oculto en pantallas
   angostas.
2. **«Nada permanente»**: la cabecera no tiene animación infinita; la ruta se dibuja una vez.
3. **El título se lee**: el contraste de título y descripción sobre el fondo (calculado con
   los colores del CSS en claro y oscuro, peor caso con la cordillera encima) llega a 4,5:1.
4. **Cada chip de atención dice qué hacer**: una línea de acción con flecha, además del
   enlace y de las clases `sev-*` que ya tenía.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.test_lv310_panel_attention import _aircraft, _record
from apps.registry.models import CostCenter

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "templates/dashboard/index.html").read_text(encoding="utf-8")
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")


def _hero_svg():
    match = re.search(r'<svg class="hero-sky".*?</svg>', TEMPLATE, re.S)
    assert match, "la cabecera perdió su dibujo"
    return match.group(0)


def _rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", IDENTITY)
    assert match, selector
    return match.group(1)


class TestTheHeroDrawing:
    def test_it_carries_no_external_resources_or_code(self):
        svg = _hero_svg()
        assert not re.search(r"https?:|<script|<image|<use|href=|on\w+=", svg, re.I)
        assert 'aria-hidden="true"' in svg

    def test_it_is_a_layered_landscape(self):
        svg = _hero_svg()
        assert svg.count("hero-ridge ") == 3
        assert "hero-plane" in svg and "route-line" in svg and "hero-grid" in svg

    def test_ridges_stay_faint(self):
        for name in ("far", "mid", "near"):
            opacity = float(
                re.search(
                    r"opacity:\s*([\d.]+)", _rule(f".hero-sky .hero-ridge--{name}")
                ).group(1)
            )
            assert 0.06 <= opacity <= 0.12, name

    def test_it_is_hidden_on_narrow_screens(self):
        assert re.search(
            r"@media \(max-width: 767\.98px\)\s*\{\s*\.hero-sky\s*\{\s*display:\s*none",
            IDENTITY,
        )

    def test_the_old_looping_route_is_gone(self):
        assert "hero-route" not in TEMPLATE and "hero-route" not in IDENTITY


class TestNothingMovesForever:
    def test_the_header_and_panel_have_no_infinite_animation(self):
        for selector in (".hero-sky", ".summary-card", ".attention", ".status-step"):
            for line in IDENTITY.splitlines():
                if selector in line and "animation" in line:
                    assert "infinite" not in line, line
        assert "ac-dash" not in IDENTITY and "ac-pulse" not in IDENTITY

    def test_the_route_is_drawn_once_and_keeps_its_end(self):
        line = next(
            row
            for row in IDENTITY.splitlines()
            if ".hero-sky .route-draw { animation" in row
        )
        assert "1.2s" in line and "forwards" in line and "infinite" not in line


def _luminance(hex_color):
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _mix(a, b, share):
    """`color-mix(in srgb, a share%, b)`, como lo calcula el navegador."""
    return tuple(
        round(int(a[i : i + 2], 16) * share + int(b[i : i + 2], 16) * (1 - share))
        for i in (1, 3, 5)
    )


def _lum_rgb(rgb):
    return _luminance("#%02x%02x%02x" % rgb)


def _contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(theme):
    """Los `--ac-*` de cada tema, tal como los declara `app.css` (el oscuro, tras su selector)."""
    dark_at = APP_CSS.index('[data-theme="dark"], [data-bs-theme="dark"] {')
    block = APP_CSS[dark_at:] if theme == "dark" else APP_CSS[:dark_at]
    return {
        name: re.search(rf"--ac-{name}:\s*(#[0-9a-fA-F]{{6}})", block).group(1)
        for name in ("surface", "text", "text-secondary", "primary")
    }


class TestTheTitleStaysReadable:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_contrast_on_the_worst_case_background(self, theme):
        tokens = _tokens(theme)

        sky = _mix(tokens["primary"], tokens["surface"], 0.14)
        # (El gris secundario NO llega a 4,5:1 con la cordillera encima: por eso la cabecera usa `text`.)
        # Peor caso: el plano más cercano (12 %) de color secundario sobre el cielo más teñido.
        sec = tokens["text-secondary"]
        worst = tuple(
            round(int(sec[i : i + 2], 16) * 0.12 + sky[k] * 0.88)
            for k, i in enumerate((1, 3, 5))
        )
        for name in ("text",):
            ratio = _contrast(_luminance(tokens[name]), _lum_rgb(worst))
            assert ratio >= 4.5, (theme, name, ratio)


def test_the_header_text_uses_the_measured_token():
    assert "var(--ac-text)" in _rule(".page-header--hero .page-description")
    assert "var(--ac-text)" in _rule(".hero-greeting")


@pytest.mark.django_db
class TestChipsSayWhatToDo:
    def _page(self, admin_client):
        centre = CostCenter.objects.create(
            code="CC-1", name="Faena", operates_flights=True
        )
        aircraft = _aircraft(cost_center=centre)
        _record(aircraft, scheduled=timezone.localdate() - timedelta(days=3))
        return admin_client.get(reverse("dashboard"))

    def test_every_chip_has_an_action_with_an_arrow_and_keeps_its_link(
        self, admin_client
    ):
        response = self._page(admin_client)
        html = response.content.decode()
        chips = re.findall(r'<a class="attention-chip[^>]*>.*?</a>', html, re.S)
        assert chips, "el panel no dibujó chips"
        for chip in chips:
            assert re.search(
                r'class="attention-action">[^<]+<span aria-hidden="true">→</span>', chip
            )
            assert 'href="' in chip and "sev-" in chip

    def test_every_key_has_a_translated_action(self):
        for key in (
            "overdue",
            "sites_without_permit",
            "maintenance_to_define",
            "awaiting_sigo",
        ):
            assert f'item.key == "{key}"' in TEMPLATE

    def test_the_greeting_names_the_user(self, admin_client):
        response = admin_client.get(reverse("dashboard"))
        assert "hero-greeting" in response.content.decode()
        name = response.wsgi_request.user.get_username()
        assert f"{name}" in response.content.decode().split("hero-greeting")[1][:80]
