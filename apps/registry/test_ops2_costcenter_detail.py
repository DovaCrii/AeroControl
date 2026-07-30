"""OPS-2: the cost center (contract) detail page with per-tab permission gating."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.operations.models import FlightPermission
from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
    Qualification,
    QualificationType,
    ResourceMovementLog,
)

TODAY = timezone.localdate()


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code)


def _url(cc):
    return reverse("costcenter-detail", args=[cc.pk])


class TestAccess:
    @pytest.mark.django_db
    def test_requires_view_costcenter_permission(self, db):
        cc = _cc()
        assert _client().get(_url(cc)).status_code == 403
        assert _client("view_costcenter").get(_url(cc)).status_code == 200


class TestTeamTab:
    @pytest.mark.django_db
    def test_hidden_without_operatorassignment_permission(self, db):
        cc = _cc()
        response = _client("view_costcenter").get(_url(cc))
        assert response.context["operator_assignments"] is None
        assert 'id="tab-team"' not in response.content.decode()

    @pytest.mark.django_db
    def test_shows_assigned_operator_and_expired_credential_badge(self, db):
        cc = _cc()
        expired_op = Operator.objects.create(
            employee_id="E1", full_name="Expired Pilot"
        )
        ok_op = Operator.objects.create(employee_id="E2", full_name="Current Pilot")
        OperatorAssignment.objects.create(
            operator=expired_op, cost_center=cc, start_date=TODAY, status="active"
        )
        OperatorAssignment.objects.create(
            operator=ok_op, cost_center=cc, start_date=TODAY, status="active"
        )
        Qualification.objects.create(
            operator=expired_op,
            qualification_type=QualificationType.objects.create(code="rpa", name="RPA"),
            issue_date=TODAY - timedelta(days=800),
            expiry_date=TODAY - timedelta(days=1),
        )

        response = _client("view_costcenter", "view_operatorassignment").get(_url(cc))

        content = response.content.decode()
        assert "Expired Pilot" in content
        assert "Current Pilot" in content
        ids = {a.operator_id for a in response.context["operator_assignments"]}
        assert ids == {expired_op.pk, ok_op.pk}
        assert response.context["expired_operator_ids"] == {expired_op.pk}


class TestFleetTab:
    @pytest.mark.django_db
    def test_hidden_without_aircraftassignment_permission(self, db):
        cc = _cc()
        response = _client("view_costcenter").get(_url(cc))
        assert response.context["aircraft_assignments"] is None

    @pytest.mark.django_db
    def test_shows_assigned_aircraft(self, db):
        cc = _cc()
        aircraft = Aircraft.objects.create(
            registration="CC-XYZ", type="RPA", model="M3", manufacturer="DJI"
        )
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc, start_date=TODAY, status="active"
        )
        response = _client("view_costcenter", "view_aircraftassignment").get(_url(cc))
        assert "CC-XYZ" in response.content.decode()


class TestPermissionsTab:
    @pytest.mark.django_db
    def test_hidden_without_flightpermission_permission(self, db):
        cc = _cc()
        response = _client("view_costcenter").get(_url(cc))
        assert response.context["flight_permissions"] is None

    @pytest.mark.django_db
    def test_shows_permission_for_this_cost_center(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        aircraft = Aircraft.objects.create(
            registration="CC-XYZ", type="RPA", model="M3", manufacturer="DJI"
        )
        permission = FlightPermission.objects.create(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=TODAY,
            valid_until=TODAY,
            location="Site",
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)
        response = _client("view_costcenter", "view_flightpermission").get(_url(cc))
        assert "P-1" in response.content.decode()


class TestDocumentsTab:
    @pytest.mark.django_db
    def test_hidden_without_document_permission(self, db):
        cc = _cc()
        response = _client("view_costcenter").get(_url(cc))
        assert response.context["documents"] is None

    @pytest.mark.django_db
    def test_shows_document_attached_to_this_cost_center(self, db):
        cc = _cc()
        doc_type = DocumentType.objects.create(code="CONTRACT", name="Contract")
        Document.objects.create(
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id=cc.pk,
            doc_type=doc_type,
            title="Signed contract",
            issue_date=TODAY,
            file_path="x",
        )
        response = _client("view_costcenter", "view_document").get(_url(cc))
        assert "Signed contract" in response.content.decode()


class TestHistoryTab:
    @pytest.mark.django_db
    def test_hidden_without_resourcemovementlog_permission(self, db):
        cc = _cc()
        response = _client("view_costcenter").get(_url(cc))
        assert response.context["movements"] is None

    @pytest.mark.django_db
    def test_shows_movement_into_this_cost_center(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Moved Pilot")
        OperatorAssignment.objects.create(
            operator=operator, cost_center=cc, start_date=TODAY, status="active"
        )
        response = _client("view_costcenter", "view_resourcemovementlog").get(_url(cc))
        content = response.content.decode()
        assert "Moved Pilot" in content
        movements = response.context["movements"]
        assert any(
            m.movement == "assigned" and m.to_cost_center_id == cc.pk for m in movements
        )
        assert ResourceMovementLog.objects.filter(to_cost_center=cc).exists()
