"""LV-366: buscador LOCAL de comunas (BCN) para elegir la ciudad del tiempo. Sin red.

El punto de cada comuna es INTERIOR a su polígono (no el centro del recuadro), el nombre se busca
sin tildes y la zona horaria es `America/Santiago` salvo Magallanes (`America/Punta_Arenas`) e
Isla de Pascua (`Pacific/Easter`). `conftest.py` hace fallar cualquier `urlopen`: si el buscador
local llamara a la red, estas pruebas lo dirían.
"""

import urllib.error

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.core import weather
from apps.core.testing import login_as
from apps.geo import administrative as admin
from apps.weather.models import UserWeatherLocation
from apps.weather.search import search_cities

VIEW = "view_userweatherlocation"


class TestNames:
    def test_accents_and_enye_do_not_matter(self):
        assert admin.normalize_name("  ÑUÑOA ") == "nunoa"
        for query in ("nunoa", "Ñuñoa", "ÑUÑOA", "  nuñoa"):
            assert [r["comuna"] for r in admin.search_comunas(query)] == ["Ñuñoa"]

    def test_exact_beats_prefix_beats_inside(self):
        names = [r["comuna"] for r in admin.search_comunas("san")]
        assert names[0].lower().startswith("san")
        exact = admin.search_comunas("Santiago")[0]
        assert exact["comuna"] == "Santiago"

    def test_order_is_stable_between_calls(self):
        assert admin.search_comunas("la") == admin.search_comunas("la")

    def test_at_most_eight_and_nonsense_is_empty(self):
        assert len(admin.search_comunas("a")) <= admin.SEARCH_LIMIT
        assert admin.search_comunas("zzzzzz") == []
        assert admin.search_comunas("   ") == []

    def test_the_unmarked_zone_is_never_offered(self):
        for entry in admin._comunas():
            if entry["region"] == "Zona sin demarcar":
                assert admin.search_comunas(entry["comuna"]) == []


class TestInteriorPoint:
    def test_every_point_falls_inside_its_own_commune(self):
        """El punto de CADA comuna resuelve a ella misma con `locate` (la regla de siempre)."""
        wrong = []
        for entry in admin._comunas():
            if entry["region"] == "Zona sin demarcar":
                continue
            found = admin.locate(*admin.interior_point(entry))
            if found is None or found["code"] != entry["code"]:
                wrong.append(entry["comuna"])
        assert wrong == []

    def test_the_bbox_centre_would_not_have_worked(self):
        """Por qué hay punto interior: el centro del recuadro cae fuera en alguna comuna."""
        outside = []
        for entry in admin._comunas():
            min_lat, min_lon, max_lat, max_lon = entry["bbox"]
            centre = ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
            found = admin.locate(*centre)
            if found is None or found["code"] != entry["code"]:
                outside.append(entry["comuna"])
        assert outside, "si ninguno cae fuera, el punto interior no haría falta"

    def test_a_ring_with_a_hole_gets_a_point_in_the_ring_not_the_hole(self):
        square = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
        hole = [(3.0, 3.0), (3.0, 7.0), (7.0, 7.0), (7.0, 3.0)]
        entry = {"rings": [square, hole], "bbox": (0.0, 0.0, 10.0, 10.0)}
        lat, lon = admin.interior_point(entry)
        inside_hole = 3 < lat < 7 and 3 < lon < 7
        assert 0 < lat < 10 and 0 < lon < 10 and not inside_hole


class TestZones:
    @pytest.mark.parametrize(
        "query,zone",
        [
            ("Providencia", "America/Santiago"),
            ("Juan Fernández", "America/Santiago"),
            ("Punta Arenas", "America/Punta_Arenas"),
            ("Natales", "America/Punta_Arenas"),
            ("Cabo de Hornos", "America/Punta_Arenas"),
            ("Isla de Pascua", "Pacific/Easter"),
        ],
    )
    def test_zone_by_commune(self, query, zone):
        assert admin.search_comunas(query)[0]["timezone"] == zone


class TestSearchPlaces:
    def test_it_answers_locally_with_no_network(self, settings):
        settings.WEATHER_ENABLED = True
        settings.WEATHER_PROVIDER = "met_norway"
        places = weather.search_places("providencia")  # `urlopen` falla si se llama
        assert places[0]["name"] == "Providencia"
        assert places[0]["admin1"].startswith("Región Metropolitana")
        assert places[0]["country"] == "Chile"
        assert places[0]["timezone"] == "America/Santiago"

    def test_local_wins_even_with_open_meteo_as_provider(self, settings):
        settings.WEATHER_ENABLED = True
        settings.WEATHER_PROVIDER = "open_meteo"
        assert weather.search_places("Ñuñoa")[0]["name"] == "Ñuñoa"

    def test_unknown_place_with_met_is_empty_and_calls_nothing(self, settings):
        settings.WEATHER_ENABLED = True
        settings.WEATHER_PROVIDER = "met_norway"
        assert weather.search_places("Oslo") == []

    def test_search_cities_sanitises_the_local_results(
        self, settings, django_user_model
    ):
        settings.WEATHER_ENABLED = True
        settings.WEATHER_SEARCH_MAX_PER_HOUR = 0
        user = django_user_model.objects.create_user("u", password="x")
        places = search_cities(user, "Punta Arenas")
        assert places[0]["label"].startswith("Punta Arenas, Región de Magallanes")
        assert places[0]["timezone"] == "America/Punta_Arenas"


class FakeResponse:
    status = 200
    headers = {}

    def __init__(self, body):
        import json

        self._body = json.dumps(body).encode()

    def read(self, limit=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


NOMINATIM = [
    {
        "name": "Oslo",
        "display_name": "Oslo, Norway",
        "lat": "59.9133",
        "lon": "10.7389",
        "address": {"state": "Oslo", "country": "Norway", "country_code": "no"},
    },
    {"name": "Broken", "lat": "999", "lon": "0"},
]


@pytest.fixture
def nominatim(settings, monkeypatch):
    cache.clear()
    settings.WEATHER_ENABLED = True
    settings.WEATHER_PROVIDER = "met_norway"
    settings.WEATHER_NOMINATIM_ENABLED = True
    settings.WEATHER_NOMINATIM_URL = "https://nominatim.example.test/search"
    settings.WEATHER_USER_AGENT = "test-agent (test-contact)"
    sent = []

    def fake(request, timeout=None):
        sent.append(request)
        return FakeResponse(NOMINATIM)

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake)
    yield sent
    cache.clear()


class TestNominatimIsOptional:
    def test_off_by_default(self, settings):
        assert settings.WEATHER_NOMINATIM_ENABLED is False
        assert weather.nominatim_enabled() is False

    def test_it_needs_a_user_agent(self, nominatim, settings):
        settings.WEATHER_USER_AGENT = ""
        assert weather.nominatim_enabled() is False
        assert weather.search_places("Oslo") == []
        assert nominatim == []

    def test_local_matches_never_reach_nominatim(self, nominatim):
        assert weather.search_places("Providencia")[0]["name"] == "Providencia"
        assert nominatim == []

    def test_a_foreign_place_goes_to_nominatim_with_its_own_agent(
        self, nominatim, settings
    ):
        settings.WEATHER_PROVIDER = "open_meteo"  # el único que usa llave
        settings.WEATHER_API_KEY = "paid-key-must-not-travel"
        places = weather.search_places("Oslo")
        assert [p["name"] for p in places] == [
            "Oslo"
        ]  # coordenadas inválidas descartadas
        assert places[0]["country_code"] == "NO"
        assert len(nominatim) == 1
        request = nominatim[0]
        assert request.get_header("User-agent") == "test-agent (test-contact)"
        assert "paid-key" not in request.full_url and "apikey" not in request.full_url
        assert "q=Oslo" in request.full_url

    def test_results_are_cached_and_one_request_per_second(self, nominatim):
        weather.search_places("Oslo")
        weather.search_places("Oslo")
        assert len(nominatim) == 1  # la misma consulta sale de la caché
        assert weather.search_places("Bergen") is None  # otra, dentro del mismo segundo
        assert len(nominatim) == 1

    def test_a_failure_is_unavailable(self, nominatim, monkeypatch):
        def boom(request, timeout=None):
            raise urllib.error.URLError("down")

        monkeypatch.setattr(weather.urllib.request, "urlopen", boom)
        assert weather.search_places("Oslo") is None


@pytest.mark.django_db
class TestTheChooser:
    def test_search_pick_and_save_a_commune(self, settings):
        settings.WEATHER_ENABLED = True
        client = login_as(VIEW, "add_userweatherlocation")
        page = client.get(reverse("weather-location"), {"q": "Ñuñoa"})
        content = page.content.decode()
        assert "Ñuñoa, Región Metropolitana de Santiago" in content
        assert "Biblioteca del Congreso Nacional" in content
        assert "OpenStreetMap" not in content
        response = client.post(reverse("weather-location"), {"q": "Ñuñoa", "pick": 0})
        assert response.status_code == 302
        row = UserWeatherLocation.objects.get(user=client.user)
        assert row.timezone == "America/Santiago"
        assert row.source == "search"

    def test_a_magallanes_commune_keeps_its_zone(self, settings):
        settings.WEATHER_ENABLED = True
        client = login_as(VIEW, "add_userweatherlocation")
        client.post(reverse("weather-location"), {"q": "Punta Arenas", "pick": 0})
        assert (
            UserWeatherLocation.objects.get(user=client.user).timezone
            == "America/Punta_Arenas"
        )

    def test_the_osm_credit_only_shows_when_nominatim_is_on(self, nominatim):
        client = login_as(VIEW)
        content = client.get(
            reverse("weather-location"), {"q": "Oslo"}
        ).content.decode()
        assert "OpenStreetMap" in content
