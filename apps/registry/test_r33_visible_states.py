"""R3.3: states that were tracked in the data but invisible in the UI.

(a) an archived operator rendered identically to an active one on the list
-- nothing in the base queryset excludes archived rows by default (only the
"is_active" filter does, and nobody defaults to it), so a former employee
sat in the roster indistinguishable from someone still on staff.
(c) Aircraft.retired already existed and already rendered (aircraft_list's
Status column, AircraftForm's status field) -- investigated, not a gap;
this file adds the regression test that was missing rather than new code.
"""

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
def test_archived_operator_is_marked_and_offers_restore_not_edit(admin_client):
    cost_center = CostCenter.objects.create(code="CC1")
    active = Operator.objects.create(
        employee_id="E1", full_name="Ana Rivas", cost_center=cost_center
    )
    left = Operator.objects.create(
        employee_id="E2", full_name="Bruno Diaz", cost_center=cost_center
    )
    left.is_active = False
    left.save(update_fields=["is_active"])

    content = admin_client.get(reverse("operator-list")).content.decode()

    assert "Archivado" in content  # LANGUAGE_CODE="es" -- runtime default
    # Row action hrefs are page-relative ("<pk>/restore/"), not the
    # reverse()d absolute path.
    assert f"{left.pk}/restore/" in content
    assert f"{active.pk}/edit/" in content
    assert f"{left.pk}/edit/" not in content


@pytest.mark.django_db
def test_retired_aircraft_is_marked_on_the_list(admin_client):
    Aircraft.objects.create(
        registration="RPA-9",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        status="retired",
    )

    content = admin_client.get(reverse("aircraft-list")).content.decode()

    assert "Retirada" in content  # LANGUAGE_CODE="es" -- runtime default
