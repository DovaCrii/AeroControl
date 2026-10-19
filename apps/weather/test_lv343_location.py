"""LV-343: ciudad predeterminada del widget del tiempo, por persona.

Se fija: 403 sin permiso en cada vista, que nadie toca la fila de otro, que las coordenadas
del POST se ignoran, el acotamiento por empresa, el tope de búsquedas, los rangos
(constraint y `clean`), CASCADE, la auditoría, `get_location_for` y la asignación a roles.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import CostCenter
from apps.weather import search as search_module
from apps.weather.locations import get_location_for
from apps.weather.models import UserWeatherLocation

URL = "weather-location"
SEARCH = "weather-search"
VIEW = "view_userweatherlocation"
ADD = "add_userweatherlocation"
CHANGE = "change_userweatherlocation"
COST = "view_costcenter"

PLACES = [
    {
        "name": "Santiago",
        "latitude": -33.4489,
        "longitude": -70.6693,
        "timezone": "America/Santiago",
        "country_code": "CL",
        "admin1": "Region Metropolitana",
    },
    {
        "name": "Santiago",
        "latitude": 19.45,
        "longitude": -70.69,
        "timezone": "America/Santo_Domingo",
        "country_code": "DO",
        "admin1": "Santiago",
    },
]


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    cache.clear()
    calls = []

    def search_places(q):
        calls.append(q)
        return list(PLACES)

    monkeypatch.setattr(
        search_module.weather_client, "search_places", search_places, raising=False
    )
    return calls


def _site(code="CC1", tenant=None, lat="-33.5", lon="-70.6", **kwargs):
    extra = {"tenant": tenant} if tenant else {}
    return CostCenter.objects.create(
        code=code, name=f"Faena {code}", latitude=lat, longitude=lon, **extra, **kwargs
    )


def _mine(client):
    return UserWeatherLocation.objects.filter(user=client.user)


@pytest.mark.django_db
class TestPermissions:
    def test_403_without_view_permission(self):
        client = login_as()
        assert client.get(reverse(URL)).status_code == 403
        assert client.get(reverse(SEARCH), {"q": "San"}).status_code == 403

    def test_anonymous_goes_to_login(self, client):
        assert client.get(reverse(URL)).status_code == 302

    def test_post_needs_add_when_there_is_no_row(self):
        client = login_as(VIEW, COST)
        site = _site()
        response = client.post(reverse(URL), {"site": str(site.pk)})
        assert response.status_code == 403
        assert not _mine(client).exists()

    def test_post_needs_change_when_there_is_a_row(self):
        client = login_as(VIEW, ADD, COST)
        site = _site()
        assert client.post(reverse(URL), {"site": str(site.pk)}).status_code == 302
        other = _site("CC2")
        # Con `add` pero sin `change` ya no puede reemplazarla.
        assert client.post(reverse(URL), {"site": str(other.pk)}).status_code == 403
        assert _mine(client).get().cost_center == site

    def test_view_only_user_can_read(self):
        assert login_as(VIEW).get(reverse(URL)).status_code == 200


@pytest.mark.django_db
class TestChoosingASite:
    def test_site_is_saved_with_its_coordinates_and_audited(self):
        client = login_as(VIEW, ADD, COST)
        site = _site(lat="-23.650000", lon="-70.400000")
        response = client.post(reverse(URL), {"site": str(site.pk)})
        assert response.status_code == 302
        row = _mine(client).get()
        assert (row.latitude, row.longitude) == (Decimal("-23.65"), Decimal("-70.4"))
        assert row.source == "cost_center" and row.cost_center == site
        event = AuditEvent.objects.get(action="weather_location_set")
        assert event.object_id == str(row.pk)

    def test_posted_coordinates_are_ignored(self):
        client = login_as(VIEW, ADD, COST)
        site = _site(lat="-23.65", lon="-70.4")
        client.post(
            reverse(URL),
            {"site": str(site.pk), "latitude": "1", "longitude": "2", "label": "X"},
        )
        row = _mine(client).get()
        assert (row.latitude, row.longitude) == (Decimal("-23.65"), Decimal("-70.4"))
        assert row.label != "X"

    def test_other_tenants_sites_are_not_offered_nor_accepted(self):
        mine = OperationalTenant.objects.create(name="Mine", slug="mine")
        theirs = OperationalTenant.objects.create(name="Theirs", slug="theirs")
        client = login_as(VIEW, ADD, COST, member_of=mine)
        own = _site("OWN", tenant=mine)
        foreign = _site("FOREIGN", tenant=theirs)
        page = client.get(reverse(URL)).content.decode()
        assert "OWN" in page and "FOREIGN" not in page
        response = client.post(reverse(URL), {"site": str(foreign.pk)})
        assert response.status_code == 400
        assert not _mine(client).exists()
        assert client.post(reverse(URL), {"site": str(own.pk)}).status_code == 302

    def test_archived_and_coordinateless_sites_are_not_offered(self):
        client = login_as(VIEW, COST)
        _site("ARCH", is_active=False)
        CostCenter.objects.create(code="NOCOORD", name="Sin coordenadas")
        _site("OKSITE")
        page = client.get(reverse(URL)).content.decode()
        assert "OKSITE" in page and "ARCH" not in page and "NOCOORD" not in page

    def test_without_view_costcenter_no_sites_and_cannot_post_one(self):
        client = login_as(VIEW, ADD)
        site = _site()
        assert "CC1" not in client.get(reverse(URL)).content.decode()
        assert client.post(reverse(URL), {"site": str(site.pk)}).status_code == 400


@pytest.mark.django_db
class TestSearching:
    def test_pick_is_resolved_on_the_server_and_ignores_posted_coordinates(self):
        client = login_as(VIEW, ADD)
        client.post(
            reverse(URL),
            {"q": "Santiago", "pick": "0", "latitude": "50", "longitude": "50"},
        )
        row = _mine(client).get()
        assert row.label == "Santiago, Region Metropolitana, CL"
        assert row.latitude == Decimal("-33.4489")
        assert row.timezone == "America/Santiago"
        assert row.source == "search" and row.cost_center is None

    def test_pick_out_of_range_is_rejected(self):
        client = login_as(VIEW, ADD)
        assert client.post(reverse(URL), {"q": "Sant", "pick": "9"}).status_code == 400
        assert not _mine(client).exists()

    def test_garbage_results_are_dropped(self, monkeypatch):
        monkeypatch.setattr(
            search_module.weather_client,
            "search_places",
            lambda q: [
                {"name": "Bad", "latitude": 999, "longitude": 0},
                {"name": "", "latitude": 1, "longitude": 1},
                {"name": "NoNum", "latitude": "x", "longitude": 1},
                "nope",
                {"name": "Good", "latitude": 1, "longitude": 1},
            ],
            raising=False,
        )
        client = login_as(VIEW)
        data = client.get(reverse(SEARCH), {"q": "Go"}).json()
        assert [r["label"] for r in data["results"]] == ["Good"]

    def test_json_search_does_not_expose_coordinates(self):
        data = login_as(VIEW).get(reverse(SEARCH), {"q": "Santiago"}).json()
        assert data["results"][0] == {
            "index": 0,
            "label": "Santiago, Region Metropolitana, CL",
        }

    def test_short_query_does_not_call_the_service(self, fake_search):
        login_as(VIEW).get(reverse(SEARCH), {"q": "S"})
        assert fake_search == []

    def test_hourly_limit_applies_to_search_and_to_the_repeat_on_post(
        self, settings, fake_search
    ):
        settings.WEATHER_SEARCH_MAX_PER_HOUR = 2
        client = login_as(VIEW, ADD)
        assert client.get(reverse(SEARCH), {"q": "San"}).status_code == 200
        assert client.get(reverse(SEARCH), {"q": "San"}).status_code == 200
        assert client.get(reverse(SEARCH), {"q": "San"}).status_code == 429
        assert client.post(reverse(URL), {"q": "San", "pick": "0"}).status_code == 400
        assert len(fake_search) == 2
        assert not _mine(client).exists()

    def test_the_limit_is_per_person(self, settings):
        settings.WEATHER_SEARCH_MAX_PER_HOUR = 1
        first, second = login_as(VIEW), login_as(VIEW, COST)
        assert first.get(reverse(SEARCH), {"q": "San"}).status_code == 200
        assert first.get(reverse(SEARCH), {"q": "San"}).status_code == 429
        assert second.get(reverse(SEARCH), {"q": "San"}).status_code == 200

    def test_page_search_shows_results_and_limit_message(self, settings):
        settings.WEATHER_SEARCH_MAX_PER_HOUR = 1
        client = login_as(VIEW)
        assert (
            "Region Metropolitana"
            in client.get(reverse(URL), {"q": "Santiago"}).content.decode()
        )
        limited = client.get(reverse(URL), {"q": "Santiago"})
        assert limited.status_code == 200
        assert "Region Metropolitana" not in limited.content.decode()


@pytest.mark.django_db
class TestOwnRowOnly:
    def test_post_only_touches_my_row_even_with_a_forged_user_field(self):
        victim = login_as(VIEW, ADD, COST)
        site = _site("V1")
        victim.post(reverse(URL), {"site": str(site.pk)})
        before = _mine(victim).get()
        attacker = login_as(VIEW, ADD, CHANGE, COST)
        other = _site("A1", lat="10", lon="10")
        attacker.post(
            reverse(URL),
            {
                "site": str(other.pk),
                "user": str(victim.user.pk),
                "id": str(before.pk),
                "pk": str(before.pk),
            },
        )
        before.refresh_from_db()
        assert before.cost_center == site
        assert _mine(attacker).get().cost_center == other

    def test_each_person_has_their_own_row(self):
        site = _site()
        a, b = login_as(VIEW, ADD, COST), login_as(VIEW, ADD, CHANGE, COST)
        a.post(reverse(URL), {"site": str(site.pk)})
        assert not _mine(b).exists()
        assert "Aún no se elige ninguna" in b.get(reverse(URL)).content.decode()
        assert UserWeatherLocation.objects.count() == 1


@pytest.mark.django_db
class TestModelRules:
    def _row(self, **kwargs):
        user = User.objects.create_user("w", password="pw")  # nosec B106
        data = dict(
            user=user,
            label="X",
            latitude=Decimal("1"),
            longitude=Decimal("1"),
            source="search",
        )
        data.update(kwargs)
        return UserWeatherLocation(**data)

    @pytest.mark.parametrize(
        "field,value", [("latitude", "91"), ("latitude", "-91"), ("longitude", "181")]
    )
    def test_clean_rejects_out_of_range(self, field, value):
        with pytest.raises(ValidationError):
            self._row(**{field: Decimal(value)}).full_clean()

    @pytest.mark.parametrize(
        "field,value", [("latitude", "90.5"), ("longitude", "-180.5")]
    )
    def test_database_constraint_rejects_out_of_range(self, field, value):
        row = self._row(**{field: Decimal(value)})
        with pytest.raises(IntegrityError), transaction.atomic():
            row.save()

    def test_site_source_needs_a_cost_center(self):
        row = self._row(source="cost_center")
        with pytest.raises(ValidationError):
            row.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            row.save()

    def test_deleting_the_user_deletes_the_preference(self):
        row = self._row()
        row.save()
        row.user.delete()
        assert not UserWeatherLocation.objects.exists()


@pytest.mark.django_db
class TestGetLocationFor:
    def _user(self):
        return User.objects.create_user("g", password="pw")  # nosec B106

    def test_none_without_row_or_default(self):
        assert get_location_for(self._user()) is None

    def test_default_is_used_when_the_person_has_no_row(self, settings):
        settings.WEATHER_DEFAULT_LABEL = "Santiago"
        settings.WEATHER_DEFAULT_LAT = "-33.45"
        settings.WEATHER_DEFAULT_LON = "-70.66"
        settings.WEATHER_DEFAULT_TZ = "America/Santiago"
        location = get_location_for(self._user())
        assert location.label == "Santiago" and location.is_default
        assert (location.latitude, location.longitude) == (-33.45, -70.66)

    def test_own_row_wins_over_the_default(self, settings):
        settings.WEATHER_DEFAULT_LABEL = "Santiago"
        settings.WEATHER_DEFAULT_LAT = "-33.45"
        settings.WEATHER_DEFAULT_LON = "-70.66"
        user = self._user()
        UserWeatherLocation.objects.create(
            user=user,
            label="Iquique",
            latitude=Decimal("-20.2"),
            longitude=Decimal("-70.1"),
            source="search",
        )
        location = get_location_for(user)
        assert location.label == "Iquique" and not location.is_default

    @pytest.mark.parametrize(
        "lat,lon", [("abc", "1"), ("95", "1"), ("1", "200"), ("", "")]
    )
    def test_bad_default_is_ignored(self, settings, lat, lon):
        settings.WEATHER_DEFAULT_LABEL = "X"
        settings.WEATHER_DEFAULT_LAT = lat
        settings.WEATHER_DEFAULT_LON = lon
        assert get_location_for(self._user()) is None


@pytest.mark.django_db
class TestRoles:
    def test_bootstrap_roles_grants_the_permissions_to_every_role(self):
        call_command("bootstrap_roles")
        for name in ("Operations", "Compliance", "Maintenance"):
            codenames = set(
                Group.objects.get(name=name).permissions.values_list(
                    "codename", flat=True
                )
            )
            assert {VIEW, ADD, CHANGE} <= codenames, name
            assert "delete_userweatherlocation" not in codenames, name

    def test_viewer_only_reads_the_city(self):
        call_command("bootstrap_roles")
        codenames = set(
            Group.objects.get(name="Viewer")
            .permissions.filter(content_type__app_label="weather")
            .values_list("codename", flat=True)
        )
        assert codenames == {VIEW}
