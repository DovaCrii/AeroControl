"""X.3: the read-only padrón API AeroLink consumes (ADR-0002 Fase 1).

The contract this locks down: AeroLink can resolve an airframe by the serial
DJI reports, sees only its own tenant's fleet, needs `view_aircraft`, and has
no way to write.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.core.testing import login_as
from apps.core.models import OperationalTenant
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def fleet(db):
    center = CostCenter.objects.create(code="CC706", name="Faena Norte")
    return {
        "center": center,
        "m3e": Aircraft.objects.create(
            registration="RPA-4401",
            type="Multirotor",
            model="M3E",
            manufacturer="DJI",
            serial_number="1581F5FHC245700D181D",
            cost_center=center,
        ),
        "wingtra": Aircraft.objects.create(
            registration="RPA-2198",
            type="Fixed wing",
            model="ONE GEN2",
            manufacturer="Wingtra",
            serial_number="2832",
        ),
    }


@pytest.mark.django_db
def test_lists_the_fleet_with_the_fields_aerolink_needs(fleet):
    response = login_as("view_aircraft").get(reverse("api-v1-registry-aircraft"))

    assert response.status_code == 200
    payload = response.json()
    registrations = {row["registration"] for row in payload["results"]}
    assert registrations == {"RPA-4401", "RPA-2198"}
    row = next(r for r in payload["results"] if r["registration"] == "RPA-4401")
    assert row["serial_number"] == "1581F5FHC245700D181D"
    assert row["manufacturer"] == "DJI"
    assert row["cost_center_code"] == "CC706"


@pytest.mark.django_db
def test_resolves_an_airframe_by_serial(fleet):
    """The lookup AeroLink actually performs: it holds a serial from DJI."""
    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft"), {"serial": "1581F5FHC245700D181D"}
    )

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["registration"] == "RPA-4401"


@pytest.mark.django_db
def test_serial_lookup_normalizes_whitespace_like_the_model_does(fleet):
    """X.1 strips whitespace from stored serials (the real repository had two
    with a spurious space). A caller passing the spaced form must still
    resolve, rather than silently getting zero results."""
    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft"), {"serial": "1581F5FHC2457 00D181D"}
    )

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["registration"] == "RPA-4401"


@pytest.mark.django_db
def test_a_partial_serial_resolves_nothing(fleet):
    """Matching a prefix would attach telemetry to the wrong airframe, which
    is worse than failing to resolve it."""
    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft"), {"serial": "1581"}
    )

    assert response.json()["results"] == []


@pytest.mark.django_db
def test_requires_view_aircraft_permission(fleet):
    """A token is not a bypass: the read contract applies to the API too."""
    assert login_as().get(reverse("api-v1-registry-aircraft")).status_code == 403


@pytest.mark.django_db
def test_anonymous_access_is_refused(fleet):
    assert Client().get(reverse("api-v1-registry-aircraft")).status_code in (401, 403)


@pytest.mark.django_db
def test_archived_aircraft_are_not_exposed(fleet):
    fleet["wingtra"].is_active = False
    fleet["wingtra"].save(update_fields=["is_active"])

    response = login_as("view_aircraft").get(reverse("api-v1-registry-aircraft"))

    registrations = {row["registration"] for row in response.json()["results"]}
    assert registrations == {"RPA-4401"}


def _other_tenant_aircraft():
    other_tenant = OperationalTenant.objects.create(
        name="Otro operador", slug="otro-operador"
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-9999",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        serial_number="OTHERTENANT1",
        tenant=other_tenant,
    )
    return other_tenant, aircraft


@pytest.mark.django_db
def test_another_tenants_airframe_does_not_leak(fleet):
    """T3.2: the API is scoped like the HTML lists. A caller with no
    membership falls back to the default tenant (visible_tenant_ids), so the
    other tenant's aircraft must be absent."""
    _other_tenant_aircraft()

    response = login_as("view_aircraft").get(reverse("api-v1-registry-aircraft"))

    registrations = {row["registration"] for row in response.json()["results"]}
    assert registrations == {"RPA-4401", "RPA-2198"}


@pytest.mark.django_db
def test_scoping_filters_both_ways(fleet):
    """The stronger half: a member of the *other* tenant sees that tenant's
    airframe and NOT the default one. Without this, the test above would also
    pass if scoping silently returned everything for everyone."""
    other_tenant, _aircraft = _other_tenant_aircraft()

    response = login_as("view_aircraft", member_of=other_tenant).get(
        reverse("api-v1-registry-aircraft")
    )

    registrations = {row["registration"] for row in response.json()["results"]}
    assert registrations == {"RPA-9999"}


@pytest.mark.django_db
def test_serial_lookup_cannot_cross_tenants(fleet):
    """Resolving by serial must not become a way around the tenant boundary."""
    other_tenant, _aircraft = _other_tenant_aircraft()

    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft"), {"serial": "OTHERTENANT1"}
    )

    assert response.json()["results"] == []


@pytest.mark.django_db
def test_detail_of_another_tenants_airframe_is_404(fleet):
    _other_tenant, aircraft = _other_tenant_aircraft()

    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft-detail", args=[aircraft.pk])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_returns_one_airframe(fleet):
    response = login_as("view_aircraft").get(
        reverse("api-v1-registry-aircraft-detail", args=[fleet["m3e"].pk])
    )

    assert response.status_code == 200
    assert response.json()["serial_number"] == "1581F5FHC245700D181D"


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_methods_exist(fleet, method):
    """ADR-0002 forbids AeroLink writing into the padrón. Enforced by not
    routing a write at all -- a superuser gets 405 too, so this cannot be
    loosened later by handing out a permission."""
    client = Client()
    user = User.objects.create_superuser("root", "root@test.com", "pw")
    assert client.login(username=user.username, password="pw")

    response = getattr(client, method)(
        reverse("api-v1-registry-aircraft"), data={}, content_type="application/json"
    )

    assert response.status_code == 405


@pytest.mark.django_db
def test_response_does_not_leak_compliance_fields(fleet):
    """The serializer is an allowlist: insurance dates, weights and VLOS are
    AeroControl's compliance business, not a telemetry gateway's."""
    fleet["m3e"].insurance_expiry = "2027-01-01"
    fleet["m3e"].save(update_fields=["insurance_expiry"])

    response = login_as("view_aircraft").get(reverse("api-v1-registry-aircraft"))

    row = next(r for r in response.json()["results"] if r["registration"] == "RPA-4401")
    for leaked in (
        "insurance_expiry",
        "insurance_status",
        "max_takeoff_weight_kg",
        "basic_weight_kg",
        "vlos",
        "parachute",
        "notes",
    ):
        assert leaked not in row
