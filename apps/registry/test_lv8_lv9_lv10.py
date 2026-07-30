"""Live-review batch: maintenance (LV-8), enriched lists (LV-9), CC prefix (LV-10a)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.maintenance.models import MaintenanceRecord
from apps.registry.forms import CostCenterForm
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


# ── LV-8: maintenance ────────────────────────────────────────────────────────
class TestMaintenanceToBeDefined:
    @pytest.mark.django_db
    def test_can_create_a_to_be_defined_record_without_date_or_assignee(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="to_be_defined",
            description="Needs inspection, date TBD",
        )
        assert record.scheduled_date is None
        assert record.performed_by == ""
        assert record.is_incomplete is True

    @pytest.mark.django_db
    def test_scheduled_record_with_date_is_not_incomplete(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h",
            scheduled_date=date(2026, 8, 1),
        )
        assert record.is_incomplete is False

    @pytest.mark.django_db
    def test_dashboard_counts_incomplete_maintenance(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="to_be_defined", description="x"
        )
        response = admin_client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert response.context["incomplete_maintenance_count"] == 1

    @pytest.mark.django_db
    def test_maintenance_form_has_no_cost_field(self, db):
        from apps.maintenance.forms import MaintenanceRecordForm

        assert "cost" not in MaintenanceRecordForm().fields


# ── LV-9: enriched lists ──────────────────────────────────────────────────────
class TestEnrichedLists:
    @pytest.mark.django_db
    def test_operator_list_shows_rut_and_qualification_badge(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1",
            full_name="Pilot One",
            rut="11.111.111-1",
            cost_center=cc,
        )
        qt = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        Qualification.objects.create(
            operator=operator,
            qualification_type=qt,
            issue_date=date(2026, 1, 1),
            expiry_date=timezone.localdate() + timedelta(days=30),
        )
        response = admin_client.get(reverse("operator-list"))
        content = response.content.decode()
        assert "11.111.111-1" in content
        assert "Current" in content or "Vigente" in content

    @pytest.mark.django_db
    def test_cost_center_list_shows_resource_counts(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One", responsible="Admin X")
        Operator.objects.create(employee_id="OP-1", full_name="P1", cost_center=cc)
        Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        response = admin_client.get(reverse("costcenter-list"))
        assert response.status_code == 200
        row = [o for o in response.context["objects"] if o.pk == cc.pk][0]
        assert row.operator_count == 1
        assert row.aircraft_count == 1
        assert "Admin X" in response.content.decode()


# ── LV-10a: CC code prefix ────────────────────────────────────────────────────
class TestCostCenterCodePrefix:
    @pytest.mark.django_db
    def test_form_prefixes_a_bare_number(self, db):
        form = CostCenterForm(data={"code": "738", "name": "New CC"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["code"] == "CC738"

    @pytest.mark.django_db
    def test_form_does_not_double_prefix(self, db):
        form = CostCenterForm(data={"code": "cc738", "name": "New CC"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["code"] == "CC738"

    @pytest.mark.django_db
    def test_form_rejects_an_empty_number(self, db):
        form = CostCenterForm(data={"code": "CC", "name": "New CC"})
        assert not form.is_valid()
        assert "code" in form.errors
