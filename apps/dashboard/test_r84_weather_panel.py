"""R8.4: the forecast on the panel -- which location it picks, and what it costs.

The provider is never called here: `forecast_for` is replaced by a recorder, so
these tests assert *how many times* and *for which (place, day)* the panel asks.
That is the property that matters -- the panel is the page every login lands on,
so one location per render is the difference between a cached call and one
outgoing request per permit per user per day.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.dashboard import views
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()

FORECAST = {
    "temperature_2m_max": 17.4,
    "temperature_2m_min": 3.9,
    "wind_speed_10m_max": 8.1,
    "wind_gusts_10m_max": 12.7,
    "precipitation_sum": 0.0,
    "precipitation_probability_max": 5,
    "condition": "cloudy",
    "units": {"wind_speed_10m_max": "m/s", "temperature_2m_max": "°C"},
    "date": TODAY.isoformat(),
}


@pytest.fixture
def asked(monkeypatch):
    """Records every (latitude, longitude, day) the panel asks for."""
    calls = []

    def forecast_for(latitude, longitude, target_date):
        calls.append((float(latitude), float(longitude), target_date))
        return FORECAST

    monkeypatch.setattr("apps.core.weather.forecast_for", forecast_for)
    return calls


def _user(*codenames):
    user = User.objects.create_user(f"panel-{'-'.join(codenames) or 'none'}", "p@x.cl")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _cc(code="CC1", **kwargs):
    return CostCenter.objects.create(code=code, name=code, **kwargs)


def _permission(cc, *, valid_from, valid_until=None, status="approved", **kwargs):
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        valid_from=valid_from,
        valid_until=valid_until or valid_from,
        location="Site",
        status=status,
        **kwargs,
    )


@pytest.mark.django_db
class TestWhichLocation:
    def test_the_next_located_flight_wins(self, asked):
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=9),
            latitude="-22.300000",
            longitude="-68.900000",
        )
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=2),
            latitude="-33.450000",
            longitude="-70.660000",
            area_name="Tranque Talabre",
        )

        context = views.panel_forecast(TODAY)

        assert asked == [(-33.45, -70.66, TODAY + timedelta(days=2))]
        assert context["weather_place"] == "Tranque Talabre"
        assert context["weather_source"] == "permission"

    def test_a_permit_already_under_way_forecasts_today(self, asked):
        """`valid_from` is the right day for a geo plan (R8.1), which is flown
        on the permit's start. On the panel it is not: a permit whose window
        opened last week would ask for a past date, which the provider answers
        with a historical run or refuses outright."""
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY - timedelta(days=5),
            valid_until=TODAY + timedelta(days=5),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        views.panel_forecast(TODAY)

        assert asked == [(-33.45, -70.66, TODAY)]

    def test_permits_with_no_coordinates_are_skipped_not_shown_empty(self, asked):
        cc = _cc()
        _permission(cc, valid_from=TODAY + timedelta(days=1))
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=4),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        views.panel_forecast(TODAY)

        assert asked == [(-33.45, -70.66, TODAY + timedelta(days=4))]

    @pytest.mark.parametrize("status", ["completed", "denied"])
    def test_finished_and_denied_permits_are_not_the_next_flight(self, asked, status):
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=1),
            latitude="-33.450000",
            longitude="-70.660000",
            status=status,
        )

        assert views.panel_forecast(TODAY)["weather"] is None
        assert asked == []

    def test_a_permit_whose_window_closed_is_not_the_next_flight(self, asked):
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY - timedelta(days=30),
            valid_until=TODAY - timedelta(days=1),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        assert views.panel_forecast(TODAY)["weather"] is None
        assert asked == []


@pytest.mark.django_db
class TestCostCenterFallback:
    def test_the_site_on_file_is_used_when_no_flight_is_located(self, asked):
        cc = _cc(latitude="-24.100000", longitude="-69.050000")

        context = views.panel_forecast(TODAY, cc)

        assert asked == [(-24.1, -69.05, TODAY)]
        assert context["weather_source"] == "cost_center"

    def test_the_filter_changes_the_location(self, asked):
        """This is what makes the panel's existing cost-center filter double as
        the location selector (R8.4 option (c) + (a))."""
        north = _cc("CC-N", latitude="-22.000000", longitude="-68.000000")
        _cc("CC-S", latitude="-38.000000", longitude="-72.000000")

        views.panel_forecast(TODAY, north)

        assert asked == [(-22.0, -68.0, TODAY)]

    def test_no_location_anywhere_shows_no_card(self, asked):
        _cc()

        assert views.panel_forecast(TODAY, _cc("CC2"))["weather"] is None
        assert asked == []

    def test_a_located_flight_still_beats_the_site(self, asked):
        cc = _cc(latitude="-24.100000", longitude="-69.050000")
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=3),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        views.panel_forecast(TODAY, cc)

        assert asked == [(-33.45, -70.66, TODAY + timedelta(days=3))]


@pytest.mark.django_db
class TestCost:
    def test_one_call_per_render_no_matter_how_many_permits(self, asked):
        """V.18/V.19 in weather form: a call per permit per page load."""
        cc = _cc()
        for offset in range(12):
            _permission(
                cc,
                valid_from=TODAY + timedelta(days=offset + 1),
                latitude="-33.450000",
                longitude="-70.660000",
            )

        views.panel_forecast(TODAY)

        assert len(asked) == 1


@pytest.mark.django_db
class TestReadContract:
    def test_the_card_does_not_bypass_view_flightpermission(self, asked):
        """The card names a folio, its site and its aircraft, so it has to obey
        the same read contract as the permission list (AGENTS.md)."""
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=2),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        context = views.panel_forecast(TODAY, None, _user())

        assert context["weather"] is None
        assert asked == []

    def test_with_the_permission_it_shows(self, asked):
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=2),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        context = views.panel_forecast(TODAY, None, _user("view_flightpermission"))

        assert context["weather"] == FORECAST

    def test_the_site_fallback_obeys_view_costcenter(self, asked):
        cc = _cc(latitude="-24.100000", longitude="-69.050000")

        assert views.panel_forecast(TODAY, cc, _user())["weather"] is None
        assert asked == []


@pytest.mark.django_db
class TestOnThePage:
    def test_the_card_renders_with_the_numbers(self, asked):
        cc = _cc()
        aircraft = Aircraft.objects.create(
            registration="RPA-2002",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        permission = _permission(
            cc,
            valid_from=TODAY + timedelta(days=2),
            latitude="-33.450000",
            longitude="-70.660000",
            area_name="Tranque Talabre",
        )
        permission.aircraft_fleet.add(aircraft)
        permission.operators.add(operator)

        response = _client(_user("view_flightpermission")).get(reverse("dashboard"))

        assert response.status_code == 200
        assert response.context["weather"] == FORECAST
        body = response.content.decode()
        # The value itself is rendered through Django's locale formatting
        # ("8,1" under es), so what is asserted here is the unit and the
        # temperature -- the two things R8.4 added to this card.
        assert "m/s" in body
        assert "17°C" in body
        assert "RPA-2002" in body
        assert "Tranque Talabre" in body

    def test_the_page_renders_fine_when_the_provider_is_down(self, monkeypatch):
        monkeypatch.setattr("apps.core.weather.forecast_for", lambda *a: None)
        cc = _cc()
        _permission(
            cc,
            valid_from=TODAY + timedelta(days=2),
            latitude="-33.450000",
            longitude="-70.660000",
        )

        response = _client(_user("view_flightpermission")).get(reverse("dashboard"))

        assert response.status_code == 200
        assert response.context["weather"] is None
