"""LV-373: la hora actual y el cambio de día en la tarjeta del tiempo (Entorno y panel).

La persona pidió saber cuál es «el renglón que se está viendo en el momento». Se fija: la columna de la
hora actual de la franja de 24 h (texto «Ahora» + hh:mm, `aria-current="time"`, una sola), el separador y
la etiqueta del primer día nuevo, la fecha en cada fila de los 7 días (hoy con `aria-current="date"`), la
fecha corta en los eventos que cruzan la medianoche, el cambio de hora de septiembre y de abril, que sin
la hora en la serie no se invente la marca, y el contraste CALCULADO del resalte. Solo presentación: las
cifras de la franja y el cálculo del pronóstico no se tocan (los guardianes de LV-347/358/365 siguen).

Las fechas son andamio declarado en cada prueba; el reloj se fija con `pin_now` o `_local_now`.
"""

import json
import re
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from apps.core import weather as weather_client
from apps.core.test_lv367_visual_base import CONTRAST, _resolve, _theme_tokens
from apps.core.testing import login_as, pin_now
from apps.weather import panel as panel_module
from apps.weather.models import UserWeatherLocation

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "apps/core/testdata/weather_panel_forecast.json"
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates/weather/_panel_card.html").read_text(encoding="utf-8")
SANTIAGO = ZoneInfo("America/Santiago")
VIEW = "view_userweatherlocation"


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


def forecast_from(first, rows):
    """Un pronóstico mínimo cuyas `rows` filas son horas REALES consecutivas desde `first` (aware)."""
    start = first.astimezone(dt_timezone.utc)
    hourly = [
        {
            "time": (start + timedelta(hours=i))
            .astimezone(SANTIAGO)
            .strftime("%Y-%m-%dT%H:%M")
        }
        for i in range(rows)
    ]
    days = sorted({h["time"][:10] for h in hourly})
    daily = [{"time": d, "sunrise": f"{d}T07:00", "sunset": f"{d}T19:30"} for d in days]
    return {"timezone": "America/Santiago", "hourly": hourly, "daily": daily}


def card_html(forecast, events=()):
    ctx = panel_module.build_card(
        SimpleNamespace(label="Santiago"), forecast, list(events)
    )
    return ctx, render_to_string("weather/_panel_card.html", ctx)


def hours_li(html):
    return re.findall(r'<li class="wx-hour[^"]*"[^>]*>.*?</li>', html, re.DOTALL)


class TestTheNowColumn:
    def test_the_current_hour_column_is_marked_once_with_text_and_time(
        self, monkeypatch
    ):
        # Andamio: lunes 26-oct-2026 22:40 (-03); la serie parte a las 22:00 y cruza la medianoche.
        now = datetime(2026, 10, 26, 22, 40, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        ctx, html = card_html(forecast_from(now.replace(minute=0), 24))
        assert [h["is_now"] for h in ctx["hours"]].count(True) == 1
        assert ctx["hours"][0]["is_now"] and ctx["now_time"] == "22:40"
        marked = [li for li in hours_li(html) if 'aria-current="time"' in li]
        assert len(marked) == 1 and "is-now" in marked[0]
        assert "Now" in marked[0] and "22:40" in marked[0]
        assert html.count('aria-current="time"') == 1

    def test_the_mark_follows_the_hour_not_the_first_column(self, monkeypatch):
        # Andamio: el pronóstico ya trae la hora anterior: la marca va en la segunda columna.
        now = datetime(2026, 10, 26, 10, 5, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        forecast = forecast_from(now.replace(minute=0), 24)
        ctx = panel_module.build_card(SimpleNamespace(label="Santiago"), forecast, [])
        assert ctx["hours"][0]["is_now"] and ctx["hours"][0]["hour"] == "10"
        # Un reloj 3 horas después mueve la marca a la hora 13, que sigue en la serie.
        pin_now(monkeypatch, now + timedelta(hours=3, minutes=10))
        ctx = panel_module.build_card(SimpleNamespace(label="Santiago"), forecast, [])
        # La franja parte en la hora actual: la marca vuelve a la primera columna, la 13.
        assert ctx["hours"][0]["hour"] == "13" and ctx["hours"][0]["is_now"]
        assert ctx["now_time"] == "13:15"

    def test_without_the_current_hour_in_the_series_nothing_is_invented(
        self, monkeypatch
    ):
        # Andamio: pronóstico de ayer (no llega a la hora actual): sin marca, sin fila de marcas.
        now = datetime(2026, 10, 28, 12, 0, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        forecast = forecast_from(datetime(2026, 10, 26, 8, tzinfo=SANTIAGO), 12)
        ctx, html = card_html(forecast)
        assert not any(h["is_now"] for h in ctx["hours"])
        assert 'aria-current="time"' not in html and "is-now" not in html
        assert ctx["strip_marks"] is False and "wx-hour-m" not in html

    def test_september_the_hour_that_does_not_exist_is_skipped_and_the_clock_is_local(
        self, monkeypatch
    ):
        # Andamio: sábado 5-sep-2026; a las 24:00 el reloj salta a 01:00. 23:40 (-04) es hora real.
        now = datetime(2026, 9, 5, 23, 40, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        ctx, html = card_html(
            forecast_from(datetime(2026, 9, 5, 22, tzinfo=SANTIAGO), 24)
        )
        labels = [h["hour"] for h in ctx["hours"]]
        assert labels[:3] == [
            "23",
            "01",
            "02",
        ]  # la franja parte en la hora actual; no hay «00»
        assert [i for i, h in enumerate(ctx["hours"]) if h["is_now"]] == [0]
        assert ctx["now_time"] == "23:40"
        # El día nuevo empieza en la primera columna que existe de él: la «01».
        assert [i for i, h in enumerate(ctx["hours"]) if h["new_day"]] == [1]

    def test_april_the_repeated_hour_marks_only_the_pass_that_is_now(self, monkeypatch):
        # Andamio: sábado 4-abr-2026; a las 24:00 el reloj vuelve a las 23:00: dos columnas «23».
        first = datetime(2026, 4, 4, 21, tzinfo=SANTIAGO)
        forecast = forecast_from(first, 24)
        assert [r["time"][11:13] for r in forecast["hourly"]][:5] == [
            "21",
            "22",
            "23",
            "23",
            "00",
        ]
        # Primera vuelta: 23:30 (-03) = 02:30 UTC; segunda: 23:30 (-04) = 03:30 UTC.
        for utc_hour, expected in ((2, 0), (3, 1)):
            pin_now(
                monkeypatch, datetime(2026, 4, 5, utc_hour, 30, tzinfo=dt_timezone.utc)
            )
            ctx = panel_module.build_card(
                SimpleNamespace(label="Santiago"), forecast, []
            )
            marked = [i for i, h in enumerate(ctx["hours"]) if h["is_now"]]
            assert ctx["now_time"] == "23:30"
            # La franja parte en la primera «23» (ambas vueltas); la marca va en la vuelta de ahora.
            assert marked == [expected]
            assert [h["hour"] for h in ctx["hours"]][:3] == ["23", "23", "00"]


class TestTheDayChange:
    def test_the_first_column_of_the_new_day_carries_the_separator_and_the_label(
        self, monkeypatch
    ):
        now = datetime(2026, 10, 26, 22, 40, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        ctx, html = card_html(forecast_from(now.replace(minute=0), 24))
        assert [i for i, h in enumerate(ctx["hours"]) if h["new_day"]] == [2]
        news = [li for li in hours_li(html) if "is-newday" in li]
        assert len(news) == 1
        assert '<span class="wx-hour-h">00</span>' in news[0]
        assert re.search(r"<span>Tue</span> <span>27</span>", news[0])
        # Ningún otro día cae en la franja de 24 h que parte a las 22:00.
        assert html.count("wx-mark-day") == 1

    def test_the_first_column_is_never_a_day_change(self, monkeypatch):
        now = datetime(2026, 10, 26, 0, 20, tzinfo=SANTIAGO)
        pin_now(monkeypatch, now)
        ctx, _html = card_html(forecast_from(now.replace(minute=0), 24))
        assert ctx["hours"][0]["hour"] == "00" and not ctx["hours"][0]["new_day"]


@pytest.fixture
def on(settings, monkeypatch):
    settings.WEATHER_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""
    forecast = weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))
    monkeypatch.setattr(
        weather_client, "panel_forecast", lambda lat, lon, zone=None: forecast
    )
    # El fixture es del 19-oct-2026 (lunes): se fija «ahora» a las 22:30.
    monkeypatch.setattr(
        panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 22, 30)
    )
    return forecast


@pytest.mark.django_db
class TestTheDaysAndTheEvents:
    def _html(self):
        client = login_as(VIEW)
        client.defaults.setdefault("HTTP_ACCEPT_LANGUAGE", "en")
        UserWeatherLocation.objects.create(
            user=client.user,
            label="Santiago",
            latitude="-33.4489",
            longitude="-70.6693",
            timezone="America/Santiago",
            source="search",
        )
        return client.get(reverse("weather-panel")).content.decode()

    def test_every_day_row_has_its_date_and_only_today_is_marked(self, on):
        html = self._html()
        rows = re.findall(r'<li class="wx-day[^"]*"[^>]*>.*?</li>', html, re.DOTALL)
        assert len(rows) == 7
        today = [r for r in rows if 'aria-current="date"' in r]
        assert len(today) == 1 and "is-today" in today[0]
        assert "Today" in today[0] and "<small>19/10</small>" in today[0]
        assert "<small>20/10</small>" in rows[1] and "Tue" in rows[1]
        assert all(re.search(r"<small>\d\d/\d\d</small>", r) for r in rows)
        assert html.count('aria-current="date"') == 1

    def test_the_card_renders_the_marks_for_the_fixture(self, on):
        html = self._html()
        assert html.count('aria-current="time"') == 1
        assert re.search(
            r'<b class="wx-mark-now">Now</b><span class="wx-mark-time">22:30', html
        )
        assert "is-newday" in html

    def test_an_event_that_crosses_days_carries_the_short_date(self):
        events = [
            {
                "type": "wind",
                "level": "warning",
                "start": "2026-10-20T23:00",
                "end": "2026-10-21T02:00",
                "value": 50,
                "unit": "km/h",
            },
            {
                "type": "gusts",
                "level": "info",
                "start": "2026-10-20T10:00",
                "end": "2026-10-20T12:00",
                "value": 70,
                "unit": "km/h",
            },
        ]
        forecast = weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))
        ctx = panel_module.build_card(
            SimpleNamespace(label="Santiago"), forecast, events
        )
        assert [e["crosses_days"] for e in ctx["events"]] == [True, False]
        html = render_to_string("weather/_panel_card.html", ctx)
        assert "Tue 20/10 23:00 – Wed 21/10 02:00" in html
        assert "Tue 10:00 – Tue 12:00" in html


class TestPresentationRules:
    def test_no_new_inline_style_script_or_animation(self):
        marks = TEMPLATE[TEMPLATE.index('<span class="wx-hour-m">') :].split("</li>")[0]
        assert "style=" not in marks
        assert "<script" not in TEMPLATE
        rules = "\n".join(re.findall(r"\.wx-(?:hour|mark|day)[^{]*\{[^}]*\}", IDENTITY))
        assert "transition" not in rules and "animation" not in rules
        assert "red" not in rules and "--sev-critical" not in rules

    def test_the_mark_is_not_only_a_colour(self):
        rule = re.search(r"\.wx-hour\.is-now \{([^}]*)\}", IDENTITY).group(1)
        assert "outline: 2px solid" in rule  # forma que sobrevive al alto contraste
        assert "background" in rule
        assert "border-left" in re.search(
            r"\.wx-hour\.is-newday \{([^}]*)\}", IDENTITY
        ).group(1)


def _mix(top, pct, bottom):
    """`color-mix(in srgb, top pct%, transparent)` dibujado sobre `bottom` (canales 0-255)."""
    return tuple(t * pct + b * (1 - pct) for t, b in zip(top, bottom, strict=True))


def _ratio(a, b):
    return CONTRAST.ratio(a, b)


@pytest.mark.parametrize("theme", ["light", "dark"])
class TestContrast:
    def _rgb(self, theme, token):
        tokens = _theme_tokens(theme)
        return CONTRAST.to_rgb(_resolve(tokens[f"--{token}"], tokens))

    def test_text_reads_on_the_highlight_even_over_the_scintillation_band(self, theme):
        surface = self._rgb(theme, "ac-surface")
        primary = self._rgb(theme, "ac-primary")
        warning = self._rgb(theme, "sev-warning-border")
        for base in (surface, _mix(warning, 0.26, surface)):  # con y sin banda debajo
            now = _mix(primary, 0.14, base)
            for text in ("ac-text", "ac-text-secondary"):
                ratio = _ratio(self._rgb(theme, text), now)
                assert ratio >= 4.5, (theme, text, round(ratio, 2))
            # El contorno es una forma: 3:1 contra el resalte que rodea y contra la tarjeta.
            assert _ratio(primary, now) >= 3, theme
        assert _ratio(primary, surface) >= 3, theme

    def test_today_row_reads_and_its_bar_is_a_shape(self, theme):
        surface = self._rgb(theme, "ac-surface")
        primary = self._rgb(theme, "ac-primary")
        row = _mix(primary, 0.12, surface)
        for text in ("ac-text", "ac-text-secondary", "sev-advisory-text"):
            ratio = _ratio(self._rgb(theme, text), row)
            assert ratio >= 4.5, (theme, text, round(ratio, 2))
        assert _ratio(primary, surface) >= 3

    def test_the_day_edge_is_a_shape_on_the_card(self, theme):
        assert _ratio(self._rgb(theme, "id-edge"), self._rgb(theme, "ac-surface")) >= 3


def test_the_skill_lists_the_pairs_and_contrast_py_passes_them():
    args = [str(ROOT / "static/css/app.css"), str(ROOT / "static/css/identity.css")]
    pairs = ["ac-primary:ac-surface", "ac-primary:id-tile", "id-edge:ac-surface"]
    skill = (ROOT / ".claude/skills/diseno-ui/SKILL.md").read_text(encoding="utf-8")
    for pair in pairs:
        assert f"--pair {pair}" in skill
    argv = [*args, "--min", "3"] + [x for p in pairs for x in ("--pair", p)]
    assert CONTRAST.main(argv) == 0
