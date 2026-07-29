from datetime import date

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.registry.models import Aircraft, CostCenter
from .models import MaintenanceHistory, MaintenanceRecord


@pytest.mark.django_db
def test_completing_maintenance_without_required_fields_shows_the_form_again():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-complete", args=[record.pk]), {})

    assert response.status_code == 200
    assert "completion_form" in response.context
    assert response.context["completion_form"].errors
    record.refresh_from_db()
    assert record.status == "in_progress"


@pytest.mark.django_db
def test_completing_maintenance_with_required_fields_records_history():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(
        reverse("maintenance-complete", args=[record.pk]),
        {
            "completed_date": "2026-07-24",
            "performed_by": "Contract workshop",
            "cost": "150.00",
            "notes": "Replaced worn part.",
        },
    )

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.status == "completed"
    assert record.performed_by == "Contract workshop"
    history = MaintenanceHistory.objects.get(record=record)
    assert history.previous_status == "in_progress"
    assert history.new_status == "completed"
    assert history.changed_by == "mechanic"


@pytest.mark.django_db
def test_record_detail_shows_completion_form_only_while_in_progress():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.get(reverse("maintenance-detail", args=[record.pk]))

    assert response.status_code == 200
    assert b'name="performed_by"' in response.content
    assert b'name="cost"' in response.content


@pytest.mark.django_db
def test_status_transition_is_audited_with_from_and_to_status():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="pending",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-start", args=[record.pk]))

    assert response.status_code == 302
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "status_changed"
    assert event.model_label == "maintenance.MaintenanceRecord"
    assert event.object_id == str(record.pk)
    assert event.metadata["from_status"] == "pending"
    assert event.metadata["to_status"] == "in_progress"


@pytest.mark.django_db
def test_rejected_status_transition_is_audited_as_rejected():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    # Already in_progress: a start (pending -> in_progress) is not a valid move.
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-start", args=[record.pk]))

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.status == "in_progress"
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "status_transition_rejected"
    assert event.model_label == "maintenance.MaintenanceRecord"
    assert event.object_id == str(record.pk)


@pytest.mark.django_db
def test_maintenance_record_with_history_cannot_be_hard_deleted():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    MaintenanceHistory.objects.create(
        record=record,
        previous_status="pending",
        new_status="in_progress",
        changed_by="mechanic",
    )

    with pytest.raises(ProtectedError):
        record.delete()
