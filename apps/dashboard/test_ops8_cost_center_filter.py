"""OPS-8: the dashboard's global cost-center filter."""

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user("dash-user", password="pw")
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _aircraft(cc, registration):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        cost_center=cc,
        status="active",
    )


@pytest.mark.django_db
def test_no_filter_counts_every_cost_center(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    cc2 = CostCenter.objects.create(code="CC2", name="Two")
    _aircraft(cc1, "CC-A1")
    _aircraft(cc2, "CC-A2")

    response = auth_client.get(reverse("dashboard"))

    assert response.status_code == 200
    assert response.context["aircraft_count"] == 2
    assert response.context["selected_cost_center"] is None


@pytest.mark.django_db
def test_filter_narrows_aircraft_and_permission_counts(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    cc2 = CostCenter.objects.create(code="CC2", name="Two")
    _aircraft(cc1, "CC-A1")
    aircraft2 = _aircraft(cc2, "CC-A2")
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
    permission = FlightPermission.objects.create(
        permission_number="P-1",
        cost_center=cc2,
        purpose="Survey",
        valid_from="2026-01-01",
        valid_until="2026-01-01",
        location="Site",
    )
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft2)

    response = auth_client.get(reverse("dashboard"), {"cost_center": cc2.pk})

    assert response.context["aircraft_count"] == 1
    assert response.context["selected_cost_center"] == cc2
    perms = {
        row["status"]: row["count"]
        for row in response.context["chart_data"]["permissions_by_status"]
    }
    assert sum(perms.values()) == 1


@pytest.mark.django_db
def test_unknown_cost_center_id_is_ignored(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    _aircraft(cc1, "CC-A1")

    response = auth_client.get(reverse("dashboard"), {"cost_center": uuid.uuid4()})

    assert response.status_code == 200
    assert response.context["selected_cost_center"] is None


@pytest.mark.django_db
def test_upcoming_expirations_spans_quals_documents_and_permissions():
    # T5.4: the dashboard's "real expiries" now covers qualifications, documents
    # and flight permissions -- not qualifications alone -- each with a link.
    from datetime import timedelta

    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    from apps.compliance.models import Document, DocumentType
    from apps.dashboard.views import upcoming_expirations
    from apps.registry.models import Qualification, QualificationType

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    soon = today + timedelta(days=10)

    cc = CostCenter.objects.create(code="CC1", name="One")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Ana", cost_center=cc
    )
    qtype = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    Qualification.objects.create(
        operator=operator, qualification_type=qtype, expiry_date=soon
    )
    aircraft = _aircraft(cc, "CC-A1")
    dtype = DocumentType.objects.create(code="airworthiness", name="Airworthiness")
    Document.objects.create(
        title="Airworthiness cert",
        doc_type=dtype,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        file_path="doc.pdf",
        issue_date=today,
        expiry_date=soon,
    )
    permission = FlightPermission.objects.create(
        permission_number="PERM-1",
        cost_center=cc,
        purpose="Survey",
        valid_from=today,
        valid_until=soon,
        location="Site",
    )
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft)

    items = upcoming_expirations(today, cutoff)

    assert len(items) == 3
    assert all(item["url"] for item in items)
    labels = " ".join(item["label"] for item in items)
    assert "Ana" in labels
    assert "Airworthiness cert" in labels
    assert "PERM-1" in labels


@pytest.mark.django_db
def test_upcoming_expirations_include_dgac_vigencias():
    # LV-29: a lapsing DGAC credential and JAC insurance join the window.
    from datetime import timedelta

    from django.utils import timezone, translation

    from apps.dashboard.views import upcoming_expirations

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    soon = today + timedelta(days=10)

    cc = CostCenter.objects.create(code="CC1", name="One")
    Operator.objects.create(
        employee_id="P1", full_name="Ana", cost_center=cc, credential_expiry=soon
    )
    aircraft = _aircraft(cc, "CC-A1")
    aircraft.insurance_expiry = soon
    aircraft.save(update_fields=["insurance_expiry"])

    # The kind label is translated; pin the language so the assertion is stable.
    with translation.override("en"):
        kinds = {item["kind"]: item for item in upcoming_expirations(today, cutoff)}

    assert "DGAC credential" in kinds
    assert "JAC insurance" in kinds
    assert kinds["DGAC credential"]["label"] == "Ana"
    assert kinds["JAC insurance"]["label"] == "CC-A1"
    assert all(item["url"] for item in kinds.values())


@pytest.mark.django_db
def test_archived_cost_center_is_ignored(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One", is_active=False)
    _aircraft(cc1, "CC-A1")

    response = auth_client.get(reverse("dashboard"), {"cost_center": cc1.pk})

    assert response.context["selected_cost_center"] is None


@pytest.mark.django_db
def test_dropdown_lists_only_active_cost_centers(auth_client):
    CostCenter.objects.create(code="CC1", name="Active One")
    CostCenter.objects.create(code="CC2", name="Archived Two", is_active=False)

    response = auth_client.get(reverse("dashboard"))

    codes = {cc.code for cc in response.context["cost_centers"]}
    assert codes == {"CC1"}
