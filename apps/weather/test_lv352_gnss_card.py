"""LV-352 fase 2: la tarjeta «Centelleo GNSS» del panel, SOLO informativa.

Se fija: el estado siempre con símbolo + texto (nunca solo color), la advertencia de que es una
referencia estadística, los enlaces a GEOCOM con `noopener noreferrer`, que no hay `<iframe>`, que
la tarjeta no habla de vuelos ni permisos, el interruptor (apagado no hay tarjeta ni consultas de
más), la fila de dos columnas, el escape, el contraste calculado en claro y oscuro y que el
movimiento viva sólo en el bloque `no-preference`, bajo `[data-ambient]`. Sin red: `urlopen` y los
sockets fallan si algo los toca, y la hora se FIJA con `pin_now`.
"""

import re
import socket
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.template import Context, Template
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from apps.core.testing import login_as, pin_now
from apps.dashboard.test_lv312_hero import _contrast, _luminance
from apps.weather.templatetags import gnss_tags

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "templates/dashboard/index.html").read_text(encoding="utf-8")
SANTIAGO = ZoneInfo("America/Santiago")

IN_WINDOW = datetime(2026, 1, 15, 23, 0, tzinfo=SANTIAGO)
OUT_OF_WINDOW = datetime(2026, 1, 15, 12, 0, tzinfo=SANTIAGO)
AFTER_PERIOD = datetime(2028, 6, 15, 12, 0, tzinfo=SANTIAGO)

ON_TEXT = "Typical higher-scintillation window: now"
OFF_TEXT = "Not in the typical window"
OUTSIDE_TEXT = "Outside the period the source indicates"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la tarjeta GNSS no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _page(monkeypatch, moment=IN_WINDOW, language="en", client=None):
    pin_now(monkeypatch, moment)
    client = client or login_as()
    return client.get(
        reverse("dashboard"), headers={"Accept-Language": language}
    ).content.decode()


def _card(content):
    return content.split('id="gnss-card"')[1].split("</section>")[0]


@pytest.mark.django_db
class TestTheState:
    def test_inside_the_window_it_says_now_with_symbol_and_until(self, monkeypatch):
        card = _card(_page(monkeypatch, IN_WINDOW))
        assert "gn-state--on" in card
        assert gettext(ON_TEXT) in card
        assert '<span class="gn-sym" aria-hidden="true">▲</span>' in card
        assert "until 03:00" in card

    def test_outside_it_says_not_in_the_window_and_the_next_one(self, monkeypatch):
        card = _card(_page(monkeypatch, OUT_OF_WINDOW))
        assert "gn-state--off" in card
        assert OFF_TEXT in card and "next: Thu 15 Jan, 21:00" in card
        assert '<span class="gn-sym" aria-hidden="true">●</span>' in card
        assert ON_TEXT not in card

    def test_after_the_period_it_invents_no_window(self, monkeypatch):
        card = _card(_page(monkeypatch, AFTER_PERIOD))
        assert "gn-state--outside" in card
        assert OUTSIDE_TEXT in card
        assert "next:" not in card and ON_TEXT not in card

    @pytest.mark.parametrize(
        "moment", [IN_WINDOW, OUT_OF_WINDOW, AFTER_PERIOD], ids=["on", "off", "outside"]
    )
    def test_the_state_is_never_only_colour(self, monkeypatch, moment):
        card = _card(_page(monkeypatch, moment))
        state = re.search(
            r'<p class="gn-state gn-state--\w+">(.*?)</p>', card, re.S
        ).group(1)
        assert re.search(r'class="gn-sym" aria-hidden="true">[▲●]<', state)
        text = re.sub(r"<[^>]+>", " ", state)
        assert re.search(r"[A-Za-z]{4,}", text.replace("▲", "").replace("●", ""))

    def test_the_spanish_card_is_translated(self, monkeypatch):
        card = _card(_page(monkeypatch, IN_WINDOW, language="es"))
        with translation.override("es"):
            assert gettext(ON_TEXT) != ON_TEXT
            assert gettext(ON_TEXT) in card
            assert gettext("Real-time data: see portal") in card
        assert ON_TEXT not in card


@pytest.mark.django_db
class TestTheContent:
    def test_statistical_reference_warning_and_what_it_is(self, monkeypatch):
        card = _card(_page(monkeypatch))
        assert (
            "Statistical reference from the source. It is not a measurement and not a"
            " go/no-go criterion"
        ) in card
        assert "RTK and PPK may lose the fixed solution" in card

    def test_it_admits_the_hours_are_our_interpretation(self, monkeypatch):
        card = _card(_page(monkeypatch))
        assert "our interpretation" in card and "21:00 to 03:00" in card

    def test_the_hours_in_the_notice_follow_the_environment(
        self, monkeypatch, settings
    ):
        settings.GNSS_SCINT_NIGHT_START = 22
        settings.GNSS_SCINT_NIGHT_END = 4
        assert "22:00 to 04:00" in _card(_page(monkeypatch))

    def test_links_to_the_portal_and_the_news_item_are_safe(self, monkeypatch):
        card = _card(_page(monkeypatch))
        assert "<iframe" not in card.lower()
        links = re.findall(r"<a [^>]*>", card)
        assert len(links) == 2
        for link in links:
            assert 'target="_blank"' in link
            assert 'rel="noopener noreferrer"' in link
        assert 'href="https://centelleo.geocom.cl"' in card
        assert (
            'href="https://www.geocom.cl/blogs/news/'
            'nuevo-portal-de-monitoreo-de-perturbaciones-ionosfericas"'
        ) in card
        assert "Real-time data: see portal" in card
        assert "GEOCOM / Trimble" in card

    def test_there_is_no_iframe_anywhere_on_the_page(self, monkeypatch):
        assert "<iframe" not in _page(monkeypatch).lower()

    def test_the_urls_from_the_environment_are_escaped(self, monkeypatch, settings):
        settings.GNSS_SCINT_PORTAL_URL = 'https://x.test/"><script>alert(1)</script>'
        content = _page(monkeypatch)
        assert "<script>alert(1)" not in content
        assert "&lt;script&gt;alert(1)" in content

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_nothing_talks_about_flying_permits_or_sites(self, monkeypatch, language):
        card = _card(_page(monkeypatch, language=language))
        text = re.sub(r"<svg.*?</svg>", "", card, flags=re.S)
        assert not re.search(
            r"\b(fly|flying|flight|flights|permit|permits|permiso|permisos|vuelo"
            r"|vuelos|faena|faenas|volar)\b",
            text,
            re.I,
        )
        assert not re.search(r"(?i)can fly|puede volar", text)


@pytest.mark.django_db
class TestTheSwitchAndTheRow:
    def test_it_is_on_by_default(self, monkeypatch):
        assert 'id="gnss-card"' in _page(monkeypatch)

    def test_switched_off_there_is_no_card_and_no_row(self, monkeypatch, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        settings.WEATHER_ENABLED = False
        content = _page(monkeypatch)
        assert "gnss-card" not in content and "gn-card" not in content
        assert "env-row" not in content

    def test_the_card_stands_alone_full_width_when_the_weather_is_off(
        self, monkeypatch, settings
    ):
        settings.WEATHER_ENABLED = False
        content = _page(monkeypatch, client=login_as("view_userweatherlocation"))
        assert 'class="env-row"' in content and "env-row--split" not in content
        assert 'id="gnss-card"' in content and 'id="wx-card"' not in content

    def test_with_the_weather_on_the_row_is_split(self, monkeypatch, settings):
        settings.WEATHER_ENABLED = True
        content = _page(monkeypatch, client=login_as("view_userweatherlocation"))
        assert 'class="env-row env-row--split"' in content
        assert content.index('id="wx-card"') < content.index('id="gnss-card"')

    def test_the_weather_alone_keeps_its_row_without_the_card(
        self, monkeypatch, settings
    ):
        settings.WEATHER_ENABLED = True
        settings.GNSS_SCINTILLATION_ENABLED = False
        content = _page(monkeypatch, client=login_as("view_userweatherlocation"))
        assert 'class="env-row"' in content and "gnss-card" not in content
        assert 'id="wx-card"' in content

    def test_the_panel_query_count_does_not_change(self, monkeypatch, settings):
        client = login_as()
        pin_now(monkeypatch, IN_WINDOW)
        settings.GNSS_SCINTILLATION_ENABLED = False
        client.get(reverse("dashboard"))  # calienta cachés de proceso
        with CaptureQueriesContext(connection) as off:
            client.get(reverse("dashboard"))
        settings.GNSS_SCINTILLATION_ENABLED = True
        with CaptureQueriesContext(connection) as on:
            client.get(reverse("dashboard"))
        assert len(on) == len(off)

    def test_the_dashboard_template_only_includes_the_tag(self):
        assert "{% gnss_card %}" in DASHBOARD
        assert "data-ambient" not in DASHBOARD
        assert not re.search(r"\bgn-", DASHBOARD)

    def test_the_tag_renders_nothing_when_off(self, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        out = Template("{% load gnss_tags %}{% gnss_card %}").render(Context({}))
        assert "gnss-card" not in out
        assert gnss_tags.gnss_card_enabled() is False


def _tokens(name):
    """(claro, oscuro) de un token de `app.css`: cada uno se declara una vez por tema, en ese orden."""
    found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", APP_CSS)
    assert len(found) == 2, name
    return found


class TestContrast:
    @pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
    @pytest.mark.parametrize(
        "text,background",
        [
            ("sev-warning-text", "sev-warning-bg"),
            ("sev-nominal-text", "sev-nominal-bg"),
            ("ac-text", "ac-surface"),
            ("ac-text-secondary", "ac-surface"),
        ],
    )
    def test_every_pair_the_card_uses_reaches_4_5_to_1(self, theme, text, background):
        ratio = _contrast(
            _luminance(_tokens(text)[theme]), _luminance(_tokens(background)[theme])
        )
        assert ratio >= 4.5, (text, background, theme, ratio)

    def test_the_css_uses_exactly_those_pairs(self):
        rules = dict(re.findall(r"(\.gn-[\w-]+)[^{]*\{([^}]*)\}", _f3b_static()))
        assert "var(--id-gn-on-fg)" in rules[".gn-state--on"]
        assert "var(--id-gn-off-fg)" in rules[".gn-state--off"]
        assert re.search(r"--id-gn-on-bg:\s*var\(--sev-warning-bg\)", _f3b_static())
        assert re.search(r"--id-gn-off-bg:\s*var\(--sev-nominal-bg\)", _f3b_static())


def _f3b_static():
    return IDENTITY[
        IDENTITY.index("/* F3b: centelleo (LV-352)") : IDENTITY.index(
            "/* ── Movimiento"
        )
    ]


def _motion_block():
    marker = "@media (prefers-reduced-motion: no-preference) {"
    start = IDENTITY.index(marker)
    depth = 0
    for index in range(start + len(marker) - 1, len(IDENTITY)):
        depth += {"{": 1, "}": -1}.get(IDENTITY[index], 0)
        if depth == 0:
            return IDENTITY[start:index]
    raise AssertionError("bloque sin cerrar")


class TestMotion:
    def test_the_static_section_has_no_animation_and_redefines_no_foreign_token(self):
        static = _f3b_static()
        assert "animation" not in static and "@keyframes" not in static
        assert not re.search(r"--(?:ac|sev)-[\w-]+\s*:|--id-(?!gn-)[\w-]+\s*:", static)
        assert re.search(r"--id-gn-on-bg\s*:", static)

    def test_every_gn_animation_is_inside_the_single_no_preference_block(self):
        assert IDENTITY.count("prefers-reduced-motion: no-preference") <= 2
        block = _motion_block()
        outside = IDENTITY.replace(block, "")
        assert not re.search(r"\.gn-[\w-]+[^{]*\{[^}]*animation", outside)
        assert IDENTITY.count("/* F3b: centelleo.") == 1
        assert "/* F3b: centelleo." in block

    def test_infinite_only_under_data_ambient_and_slow(self):
        lines = [
            line
            for line in IDENTITY.splitlines()
            if "gn-" in line and "infinite" in line
        ]
        assert lines
        for line in lines:
            assert "[data-ambient]" in line, line
            assert float(re.search(r"\s([\d.]+)s\s", line).group(1)) >= 6, line

    def test_only_transform_and_opacity_are_animated(self):
        found = re.findall(r"@keyframes gn-[\w-]+ \{(.*)\}", _motion_block())
        assert len(found) == 2
        for keyframes in found:
            props = set(re.findall(r"([\w-]+):", keyframes))
            assert props <= {"transform", "opacity"}, props

    @pytest.mark.django_db
    def test_the_card_is_ambient_and_animates_at_most_eight_nodes(self, monkeypatch):
        content = _page(monkeypatch)
        assert re.search(r'<section id="gnss-card"[^>]*\bdata-ambient\b', content)
        animated = re.findall(
            r'class="[^"]*\bgn-(?:wave|sat--mid)(?![\w-])', _card(content)
        )
        assert 0 < len(animated) <= 8
