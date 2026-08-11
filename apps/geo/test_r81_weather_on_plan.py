"""R8.1: the forecast panel on a geo plan's ficha (ISO 8.1).

The provider is monkeypatched -- these check what the *view* does with a
forecast (and without one), not the HTTP client, which apps/core/
test_r81_weather.py covers.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.registry.models import CostCenter


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _plan_with_area(*, with_permission=True, with_bbox=True):
    from apps.operations.models import FlightPermission

    center = CostCenter.objects.create(code="CC1", name="Uno")
    user = User.objects.create_user("owner", password="pw")
    permission = None
    if with_permission:
        permission = FlightPermission.objects.create(
            cost_center=center,
            purpose="photogrammetry",
            valid_from=date(2026, 8, 20),
            valid_until=date(2026, 8, 21),
            location="Faena Norte",
        )
    plan = GeoPlan.objects.create(
        title="Plan",
        cost_center=center,
        created_by=user,
        status="draft",
        flight_permission=permission,
    )
    bbox = (
        {
            "bbox_west": -71.0,
            "bbox_south": -34.0,
            "bbox_east": -70.0,
            "bbox_north": -33.0,
        }
        if with_bbox
        else {}
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content={"schema_version": 1, "children": []},
        content_checksum="0" * 64,
        source="import",
        created_by=user,
        **bbox,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


FORECAST = {
    "wind_speed_10m_max": 18.4,
    "wind_gusts_10m_max": 31.0,
    "precipitation_sum": 0.0,
    "precipitation_probability_max": 5,
    "units": {"wind_speed_10m_max": "km/h", "precipitation_sum": "mm"},
    "date": "2026-08-20",
}


@pytest.mark.django_db
def test_shows_the_forecast_for_the_permit_start_date(monkeypatch):
    from apps.core import weather

    asked = {}

    def fake_forecast(latitude, longitude, target_date):
        asked.update(lat=latitude, lon=longitude, day=target_date)
        return FORECAST

    monkeypatch.setattr(weather, "forecast_for", fake_forecast)
    plan = _plan_with_area()

    response = _client("view_geoplan").get(reverse("geo-plan-detail", args=[plan.pk]))
    content = response.content.decode()

    assert response.context["weather"] == FORECAST
    # The centroid of the bbox, and the day the linked permit begins -- not today.
    assert asked["lat"] == -33.5
    assert asked["lon"] == -70.5
    assert asked["day"] == date(2026, 8, 20)
    # Rendered numbers go through Django's localization, so under the project
    # default (LANGUAGE_CODE="es") 18.4 reaches the page as "18,4".
    assert "18,4" in content
    assert "31" in content
    assert "km/h" in content


@pytest.mark.django_db
def test_panel_absent_when_the_provider_gives_nothing(monkeypatch):
    """A provider outage must leave the page working, just without the panel."""
    from apps.core import weather

    monkeypatch.setattr(weather, "forecast_for", lambda *a: None)
    plan = _plan_with_area()

    response = _client("view_geoplan").get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.status_code == 200
    assert response.context["weather"] is None
    assert "Weather forecast" not in response.content.decode()


@pytest.mark.django_db
def test_no_lookup_without_a_bounding_box(monkeypatch):
    """No area means no place to forecast for -- and no request attempted."""
    from apps.core import weather

    calls = []
    monkeypatch.setattr(weather, "forecast_for", lambda *a: calls.append(a))
    plan = _plan_with_area(with_bbox=False)

    response = _client("view_geoplan").get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.context["weather"] is None
    assert calls == []


@pytest.mark.django_db
def test_no_lookup_without_a_linked_permit(monkeypatch):
    """Without a permit there is no flight date; a forecast for "today" on a
    plan flown next month would be worse than none."""
    from apps.core import weather

    calls = []
    monkeypatch.setattr(weather, "forecast_for", lambda *a: calls.append(a))
    plan = _plan_with_area(with_permission=False)

    response = _client("view_geoplan").get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.context["weather"] is None
    assert calls == []


@pytest.mark.django_db
def test_page_still_renders_with_the_feature_disabled(settings):
    """The real default: WEATHER_ENABLED=False, nothing monkeypatched, and the
    page must not attempt or need a network call."""
    settings.WEATHER_ENABLED = False
    plan = _plan_with_area()

    response = _client("view_geoplan").get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.status_code == 200
    assert response.context["weather"] is None
