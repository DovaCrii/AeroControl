"""R3.2: no registry list defined `Meta.ordering`, so all three fell back to
SearchMixin's created_at fallback -- insertion order, not something a user
reading a printed list expects."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


@pytest.mark.django_db
def test_cost_center_list_orders_by_extracted_number_not_alphabetically(
    admin_client,
):
    """ "CC110" sorts before "CC2" as plain text -- `code` is a CharField, so
    the fix is ordering by length first (groups same-digit-count codes
    together) and only then alphabetically, which gives the right order for
    a same-prefix numeric series without a DB-specific regex function."""
    CostCenter.objects.create(code="CC110")
    CostCenter.objects.create(code="CC2")
    CostCenter.objects.create(code="CC1")
    CostCenter.objects.create(code="CC100")

    response = admin_client.get(reverse("costcenter-list"))

    codes = [cc.code for cc in response.context["objects"]]
    assert codes == ["CC1", "CC2", "CC100", "CC110"]


@pytest.mark.django_db
def test_aircraft_list_orders_by_registration():
    User.objects.create_superuser("admin2", "admin2@test.com", "password")
    client = Client()
    assert client.login(username="admin2", password="password")
    Aircraft.objects.create(
        registration="RPA-2002", type="RPA", model="M", manufacturer="DJI"
    )
    Aircraft.objects.create(
        registration="RPA-2001", type="RPA", model="M", manufacturer="DJI"
    )
    Aircraft.objects.create(
        registration="RPA-2003", type="RPA", model="M", manufacturer="DJI"
    )

    response = client.get(reverse("aircraft-list"))

    registrations = [a.registration for a in response.context["objects"]]
    assert registrations == ["RPA-2001", "RPA-2002", "RPA-2003"]


@pytest.mark.django_db
def test_operator_list_orders_alphabetically_by_full_name():
    User.objects.create_superuser("admin3", "admin3@test.com", "password")
    client = Client()
    assert client.login(username="admin3", password="password")
    Operator.objects.create(employee_id="E1", full_name="Zoe Vergara")
    Operator.objects.create(employee_id="E2", full_name="Ana Rivas")
    Operator.objects.create(employee_id="E3", full_name="Mateo Soto")

    response = client.get(reverse("operator-list"))

    names = [op.full_name for op in response.context["objects"]]
    assert names == ["Ana Rivas", "Mateo Soto", "Zoe Vergara"]
