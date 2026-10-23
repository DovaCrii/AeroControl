"""LV-358 (E3): la banda de centelleo GNSS sobre la franja de 24 h del Tiempo.

La ventana típica (puesta del pronóstico + `GNSS_SCINT_SUNSET_OFFSET_MIN`, fin de siempre) se sombrea en
la franja de la tarjeta, calculada con el pronóstico YA cargado: sin consulta ni salida a la red nuevas.
Se fija: el cambio de hora de septiembre (una hora que no existe) y el de abril (una hora repetida), la
ventana que cruza la medianoche, la temporada, los interruptores, que la banda retire el guiño de
estrellas de la escena, que lleve trama y leyenda con texto (no sólo color) y que no use el rojo.

El reloj no entra: la franja se arma desde las filas del propio pronóstico, y las fechas son andamio
declarado en cada prueba.
"""

import json
import re
import socket
import urllib.request
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import weather as weather_client
from apps.core.testing import login_as
from apps.weather import panel as panel_module
from apps.weather.models import UserWeatherLocation

SANTIAGO = ZoneInfo("America/Santiago")
FIXTURE = Path(weather_client.__file__).parent / "testdata/weather_panel_forecast.json"
STEP = panel_module.STRIP_STEP
VIEW = "view_userweatherlocation"


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la banda no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def forecast_from(first, rows, sunsets):
    """Un pronóstico mínimo cuyas `rows` filas son horas REALES consecutivas desde `first` (aware).

    La hora de pared sale del instante, así que el salto de septiembre y la hora repetida de abril
    quedan como las entrega el pronóstico: en hora local, sin zona."""
    start = first.astimezone(dt_timezone.utc)
    hourly = [
        {
            "time": (start + timedelta(hours=i))
            .astimezone(SANTIAGO)
            .strftime("%Y-%m-%dT%H:%M")
        }
        for i in range(rows)
    ]
    daily = [
        {"time": day, "sunrise": f"{day}T07:00", "sunset": f"{day}T{sunset}"}
        for day, sunset in sunsets.items()
    ]
    return {"timezone": "America/Santiago", "hourly": hourly, "daily": daily}


def band_of(forecast):
    hours = panel_module._hour_rows(forecast, datetime(2000, 1, 1), 3.6)
    return panel_module.gnss_band(forecast, hours), hours


def total_width(band):
    return sum(seg["width"] for seg in band["segments"])


class TestTheWindowOnTheStrip:
    def test_a_window_that_crosses_midnight_enters_whole_and_in_two_pieces(self):
        # Andamio: 19-oct-2026 22:00 en adelante, puesta 19:50 (+60 = 20:50); sin cambio de hora cerca.
        first = datetime(2026, 10, 19, 22, tzinfo=SANTIAGO)
        forecast = forecast_from(
            first, 24, {"2026-10-19": "19:50", "2026-10-20": "19:50"}
        )
        band, hours = band_of(forecast)
        assert len(hours) == 24
        head, tail = band["segments"]
        # La ventana de la tarde anterior sigue en curso y termina a las 03:00: cinco horas desde el borde.
        assert head == {"left": 0, "width": 5 * STEP}
        # La de esta tarde arranca a las 20:50, 22 h 50 min después de la primera hora.
        assert tail["left"] == pytest.approx((22 + 50 / 60) * STEP, abs=1)
        assert tail["left"] + tail["width"] == pytest.approx(24 * STEP, abs=1)
        assert band["label"] == "20:50–03:00"

    def test_september_skips_an_hour_and_the_band_measures_real_hours(self):
        # Andamio: sábado 5-sep-2026 (el salto es a las 24:00 → 01:00), puesta 19:30, +60 = 20:30.
        first = datetime(2026, 9, 5, 18, tzinfo=SANTIAGO)
        forecast = forecast_from(
            first, 24, {"2026-09-05": "19:30", "2026-09-06": "19:31"}
        )
        band, hours = band_of(forecast)
        labels = [h["hour"] for h in hours]
        assert "00" not in labels  # la hora de pared que no existe
        (segment,) = band["segments"]
        assert segment["left"] == pytest.approx(2 * STEP + STEP / 2, abs=1)
        # 20:30 (-04) hasta 03:00 (-03) son 5,5 horas REALES; por reloj de pared serían 6,5.
        assert total_width(band) == pytest.approx(5.5 * STEP, abs=1)

    def test_april_repeats_an_hour_and_the_band_does_not_fold_back(self):
        # Andamio: sábado 4-abr-2026 (a las 24:00 el reloj vuelve a las 23:00), puesta 18:50, +60 = 19:50.
        first = datetime(2026, 4, 4, 18, tzinfo=SANTIAGO)
        forecast = forecast_from(
            first, 24, {"2026-04-04": "18:50", "2026-04-05": "18:49"}
        )
        band, hours = band_of(forecast)
        labels = [h["hour"] for h in hours]
        assert labels.count("23") == 2  # la hora de pared repetida
        (segment,) = band["segments"]
        assert segment["left"] == pytest.approx(STEP + 50 / 60 * STEP, abs=1)
        # 19:50 (-03) hasta 03:00 (-04): 8 h 10 min reales.
        assert total_width(band) == pytest.approx((8 + 10 / 60) * STEP, abs=1)

    def test_the_second_pass_of_the_repeated_hour_is_a_later_instant(self):
        # La puesta de las 22:30 es un andamio inventado para que el inicio de la ventana (23:30) caiga EN
        # la hora repetida de abril: la fila de la segunda vuelta de las 23:00 tiene que valer una hora
        # real después de la primera, o contaría sólo media hora de las 4,5 que dura la ventana.
        first = datetime(2026, 4, 4, 18, tzinfo=SANTIAGO)
        forecast = forecast_from(first, 24, {"2026-04-04": "22:30"})
        band, hours = band_of(forecast)
        assert [h["hour"] for h in hours].count("23") == 2
        (segment,) = band["segments"]
        assert segment["left"] == pytest.approx(5 * STEP + STEP / 2, abs=1)
        assert total_width(band) == pytest.approx(
            4.5 * STEP, abs=1
        )  # 23:30 (-03) a 03:00 (-04)

    def test_a_strip_that_starts_after_midnight_still_gets_last_nights_window(self):
        # Andamio: la franja arranca a la 01:00 del 20-oct; la ventana es la de la tarde del 19.
        first = datetime(2026, 10, 20, 1, tzinfo=SANTIAGO)
        forecast = forecast_from(
            first, 24, {"2026-10-19": "19:50", "2026-10-20": "19:50"}
        )
        band, _ = band_of(forecast)
        assert band["segments"][0] == {"left": 0, "width": 2 * STEP}  # hasta las 03:00

    def test_the_offset_setting_moves_the_start(self, settings):
        settings.GNSS_SCINT_SUNSET_OFFSET_MIN = 0
        first = datetime(2026, 10, 19, 22, tzinfo=SANTIAGO)
        forecast = forecast_from(
            first, 24, {"2026-10-19": "19:50", "2026-10-20": "19:50"}
        )
        band, _ = band_of(forecast)
        tail = band["segments"][1]
        assert tail["left"] == pytest.approx((21 + 50 / 60) * STEP, abs=1)

    def test_without_a_sunset_the_fixed_hours_are_used(self):
        first = datetime(2026, 10, 19, 22, tzinfo=SANTIAGO)
        forecast = forecast_from(first, 24, {})
        band, _ = band_of(forecast)
        tail = band["segments"][1]
        # 21:00 fijo: 23 h después de las 22:00.
        assert tail["left"] == pytest.approx(23 * STEP, abs=1)

    def test_outside_the_season_there_is_no_band(self):
        first = datetime(2026, 6, 10, 12, tzinfo=SANTIAGO)  # junio: fuera de sep–abr
        forecast = forecast_from(
            first, 24, {"2026-06-10": "17:45", "2026-06-11": "17:45"}
        )
        assert band_of(forecast)[0] is None

    def test_after_the_covered_years_there_is_no_band(self):
        first = datetime(2028, 6, 10, 12, tzinfo=SANTIAGO)
        forecast = forecast_from(first, 24, {"2028-06-10": "17:45"})
        assert band_of(forecast)[0] is None

    def test_the_switch_off_means_no_band(self, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        first = datetime(2026, 10, 19, 22, tzinfo=SANTIAGO)
        forecast = forecast_from(first, 24, {"2026-10-19": "19:50"})
        assert band_of(forecast)[0] is None

    def test_no_hours_no_band(self):
        assert panel_module.gnss_band({"timezone": "America/Santiago"}, []) is None


@pytest.fixture
def on(settings, monkeypatch):
    settings.WEATHER_ENABLED = True
    settings.GNSS_SCINTILLATION_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""
    forecast = weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))
    monkeypatch.setattr(
        weather_client, "panel_forecast", lambda lat, lon, zone=None: forecast
    )
    # El fixture es del 19-oct-2026: se fija «ahora» a las 22:00 (ventana activa).
    monkeypatch.setattr(
        panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 22, 0)
    )
    return forecast


def _city(client):
    return UserWeatherLocation.objects.create(
        user=client.user,
        label="Santiago",
        latitude="-33.4489",
        longitude="-70.6693",
        timezone="America/Santiago",
        source="search",
    )


@pytest.mark.django_db
class TestTheCard:
    def _html(self, client=None):
        client = client or login_as(VIEW)
        client.defaults.setdefault("HTTP_ACCEPT_LANGUAGE", "en")
        _city(client)
        return client.get(reverse("weather-panel")).content.decode()

    def test_the_card_draws_the_band_behind_the_hours_with_its_legend(self, on):
        html = self._html()
        bands = re.findall(r'<span class="wx-gnss-band"[^>]*>', html)
        assert bands and all('aria-hidden="true"' in band for band in bands)
        strip = html.split('<div class="wx-strip-inner"')[1].split(
            '<ol class="wx-hours">'
        )[0]
        assert strip.count("wx-gnss-band") == len(
            bands
        )  # dentro de la franja, antes de las horas
        assert re.search(
            r"Typical scintillation window \(GNSS\): \d\d:\d\d–\d\d:\d\d", html
        )
        assert '<i class="wx-key-gnss" aria-hidden="true">' in html

    def test_the_band_comes_from_the_forecast_already_loaded(self, on, monkeypatch):
        calls = []
        real = weather_client.panel_forecast
        monkeypatch.setattr(
            weather_client,
            "panel_forecast",
            lambda a, b, z=None: calls.append(1) or real(a, b, z),
        )
        client = login_as(VIEW)
        _city(client)
        client.get(reverse("weather-panel"))
        assert len(calls) == 1  # un solo pedido del pronóstico, como antes de la banda

    def test_the_band_adds_no_query(self, on, settings):
        client = login_as(VIEW)
        _city(client)
        settings.GNSS_SCINTILLATION_ENABLED = False
        client.get(reverse("weather-panel"))  # calienta cachés de proceso
        with CaptureQueriesContext(connection) as off:
            client.get(reverse("weather-panel"))
        settings.GNSS_SCINTILLATION_ENABLED = True
        with CaptureQueriesContext(connection) as with_band:
            client.get(reverse("weather-panel"))
        assert len(with_band) == len(off)

    def test_with_the_switch_off_there_is_neither_band_nor_legend(self, on, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        html = self._html()
        assert "wx-gnss-band" not in html and "Typical scintillation window" not in html

    def test_the_band_retires_the_wink_of_the_scene(self, on):
        html = self._html()
        assert "wx-gnss-band" in html
        assert "sky-star--tw" not in html

    def test_the_legend_is_translated(self, on):
        with translation.override("es"):
            client = login_as(VIEW)
            client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
            html = self._html(client)
        assert "Ventana típica de centelleo (GNSS):" in html
        assert "Typical scintillation window" not in html

    def test_the_context_carries_the_band_for_the_template(self, on):
        context = panel_module.build_card(SimpleNamespace(label="Santiago"), on, [])
        assert context["gnss_band"]["segments"]
        html = render_to_string("weather/_panel_card.html", context)
        assert html.count('class="wx-gnss-band"') == len(
            context["gnss_band"]["segments"]
        )


class TestTheStylesheet:
    IDENTITY = (
        Path(__file__).resolve().parents[2] / "static/css/identity.css"
    ).read_text(encoding="utf-8")

    def _rules(self):
        return re.findall(
            r"(\.wx-(?:gnss-band|key-gnss)[^{]*)\{([^}]*)\}", self.IDENTITY
        )

    def test_the_band_has_a_pattern_and_never_the_critical_red(self):
        rules = dict(self._rules())
        band = rules[".wx-gnss-band "]
        assert "repeating-linear-gradient" in band  # trama: el color no va solo
        assert "sev-warning" in band
        assert not any(
            "critical" in body or "danger" in body for body in rules.values()
        )

    def test_the_band_does_not_animate_and_never_blocks_the_hours(self):
        band = dict(self._rules())[".wx-gnss-band "]
        assert "animation" not in band and "transition" not in band
        assert "pointer-events: none" in band
