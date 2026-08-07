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
def test_upcoming_expirations_assigns_the_shared_urgency_bucket():
    """R1.1: the panel used to be a flat gray badge no matter how soon
    something expires. Each item now carries the same overdue/due_7/due_15/
    due_30 bucket as the compliance report and the Kanban card (B3.3), not a
    fourth urgency scale."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.dashboard.views import upcoming_expirations
    from apps.registry.models import Qualification, QualificationType

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)

    cc = CostCenter.objects.create(code="CC1", name="One")
    qtype = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    within_7 = Operator.objects.create(
        employee_id="P1", full_name="Due soon", cost_center=cc
    )
    within_15 = Operator.objects.create(
        employee_id="P2", full_name="Due mid", cost_center=cc
    )
    within_30 = Operator.objects.create(
        employee_id="P3", full_name="Due later", cost_center=cc
    )
    Qualification.objects.create(
        operator=within_7,
        qualification_type=qtype,
        expiry_date=today + timedelta(days=5),
    )
    Qualification.objects.create(
        operator=within_15,
        qualification_type=qtype,
        expiry_date=today + timedelta(days=10),
    )
    Qualification.objects.create(
        operator=within_30,
        qualification_type=qtype,
        expiry_date=today + timedelta(days=25),
    )

    buckets = {
        item["label"]: item["bucket"] for item in upcoming_expirations(today, cutoff)
    }

    assert buckets["Due soon — Serie Mavic"] == "due_7"
    assert buckets["Due mid — Serie Mavic"] == "due_15"
    assert buckets["Due later — Serie Mavic"] == "due_30"


@pytest.mark.django_db
def test_permission_without_dgac_folio_does_not_render_the_word_none():
    """R1.2: verified live on the demo -- a permit with no DGAC folio showed
    up on this panel as "Flight permission None", not blank. Same root cause
    as the calendar's _permission_title, different code path."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.dashboard.views import upcoming_expirations

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)

    cc = CostCenter.objects.create(code="CC1", name="One")
    permission = FlightPermission.objects.create(
        cost_center=cc,
        purpose="Audiovisual",
        valid_from=today,
        valid_until=today + timedelta(days=5),
        location="Site",
    )
    assert permission.permission_number is None

    items = upcoming_expirations(today, cutoff)

    assert len(items) == 1
    assert items[0]["label"] == "En proceso"


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
def test_expiring_soon_kpi_tile_links_to_the_panel_with_severity(auth_client):
    """R1.1: "Expiring in 30 days" was the one KPI tile that was not a link,
    and every row below it was a flat gray badge no matter how urgent. Both
    were true regardless of how the auditor's guide reads: this is exactly
    the panel meant to surface DGAC/JAC compliance state at a glance."""
    from datetime import timedelta

    from django.utils import timezone

    cc = CostCenter.objects.create(code="CC1", name="One")
    Operator.objects.create(
        employee_id="P1",
        full_name="Due Soon Operator",
        cost_center=cc,
        credential_expiry=timezone.localdate() + timedelta(days=3),
    )

    response = auth_client.get(reverse("dashboard"))
    content = response.content.decode()

    assert 'href="#upcoming-expirations"' in content
    assert 'id="upcoming-expirations"' in content
    assert "Due Soon Operator" in content
    assert "Vence en 7 días" in content


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
