"""OPS-1: per-resource assignments, the denormalization signal and the log."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
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


def _operator(**kwargs):
    return Operator.objects.create(
        employee_id=kwargs.pop("employee_id", "E1"),
        full_name=kwargs.pop("full_name", "Pilot One"),
        **kwargs,
    )


def _cc(code):
    return CostCenter.objects.create(code=code, name=code)


class TestOverlap:
    @pytest.mark.django_db
    def test_overlapping_active_assignment_is_rejected(self, db):
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        clashing = OperatorAssignment(
            operator=op, cost_center=cc2, start_date=TODAY, status="active"
        )
        with pytest.raises(ValidationError):
            clashing.full_clean()

    @pytest.mark.django_db
    def test_consecutive_non_overlapping_assignments_are_allowed(self, db):
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        OperatorAssignment.objects.create(
            operator=op,
            cost_center=cc1,
            start_date=TODAY - timedelta(days=10),
            end_date=TODAY - timedelta(days=1),
            status="ended",
        )
        later = OperatorAssignment(
            operator=op, cost_center=cc2, start_date=TODAY, status="active"
        )
        later.full_clean()  # must not raise


class TestDenormalizationAndLog:
    @pytest.mark.django_db
    def test_creating_assignment_sets_cost_center_and_logs_assigned(self, db):
        op = _operator()
        cc1 = _cc("CC1")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        op.refresh_from_db()
        assert op.cost_center_id == cc1.pk
        log = ResourceMovementLog.objects.get(resource_id=op.pk)
        assert log.resource_kind == "operator"
        assert log.movement == "assigned"
        assert log.to_cost_center_id == cc1.pk
        assert log.from_cost_center_id is None

    @pytest.mark.django_db
    def test_changing_cost_center_logs_reassigned(self, db):
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        assignment = OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        assignment.cost_center = cc2
        assignment.save(update_fields=["cost_center", "updated_at"])
        op.refresh_from_db()
        assert op.cost_center_id == cc2.pk
        latest = ResourceMovementLog.objects.filter(resource_id=op.pk).first()
        assert latest.movement == "reassigned"
        assert latest.from_cost_center_id == cc1.pk
        assert latest.to_cost_center_id == cc2.pk

    @pytest.mark.django_db
    def test_archiving_assignment_releases_and_logs(self, db):
        op = _operator()
        cc1 = _cc("CC1")
        assignment = OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        assignment.is_active = False
        assignment.save(update_fields=["is_active", "updated_at"])
        op.refresh_from_db()
        assert op.cost_center_id is None
        latest = ResourceMovementLog.objects.filter(resource_id=op.pk).first()
        assert latest.movement == "released"

    @pytest.mark.django_db
    def test_changed_by_user_is_recorded_when_set_on_the_instance(self, db):
        op = _operator()
        cc1 = _cc("CC1")
        user = User.objects.create_user("mover", password="pw")
        assignment = OperatorAssignment(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        assignment._changed_by_user = user
        assignment.save()
        log = ResourceMovementLog.objects.get(resource_id=op.pk)
        assert log.changed_by_user_id == user.pk

    @pytest.mark.django_db
    def test_aircraft_assignment_denormalizes_too(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-AAA", type="RPA", model="M3", manufacturer="DJI"
        )
        cc1 = _cc("CC1")
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc1, start_date=TODAY, status="active"
        )
        aircraft.refresh_from_db()
        assert aircraft.cost_center_id == cc1.pk
        assert ResourceMovementLog.objects.filter(
            resource_kind="aircraft", resource_id=aircraft.pk, movement="assigned"
        ).exists()


class TestAppendOnlyLog:
    @pytest.mark.django_db
    def test_log_cannot_be_updated_or_deleted(self, db):
        op = _operator()
        OperatorAssignment.objects.create(
            operator=op, cost_center=_cc("CC1"), start_date=TODAY, status="active"
        )
        qs = ResourceMovementLog.objects.filter(resource_id=op.pk)
        with pytest.raises(ValidationError):
            qs.update(detail="x")
        with pytest.raises(ValidationError):
            qs.delete()
        with pytest.raises(ValidationError):
            qs.first().delete()


class TestOperatorAssignmentViews:
    @pytest.mark.django_db
    def test_list_requires_view_permission(self, db):
        assert _client().get(reverse("operatorassignment-list")).status_code == 403
        response = _client("view_operatorassignment").get(
            reverse("operatorassignment-list")
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_create_requires_add_permission(self, db):
        op = _operator()
        cc = _cc("CC1")
        payload = {
            "operator": op.pk,
            "cost_center": cc.pk,
            "start_date": TODAY.isoformat(),
            "status": "active",
            "purpose": "",
        }
        url = reverse("operatorassignment-create")
        assert _client("view_operatorassignment").post(url, payload).status_code == 403

        response = _client("add_operatorassignment").post(url, payload)
        assert response.status_code == 302
        assert OperatorAssignment.objects.filter(operator=op, cost_center=cc).exists()

    @pytest.mark.django_db
    def test_create_rejects_overlap_via_form(self, db):
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        payload = {
            "operator": op.pk,
            "cost_center": cc2.pk,
            "start_date": TODAY.isoformat(),
            "status": "active",
            "purpose": "",
        }
        response = _client("add_operatorassignment").post(
            reverse("operatorassignment-create"), payload
        )
        # HtmxFormMixin.form_invalid re-renders 200/422 for the modal fragment;
        # a plain (non-HTMX) POST falls through to the normal invalid-form 200.
        assert response.status_code == 200
        assert OperatorAssignment.objects.filter(cost_center=cc2).count() == 0


class TestAircraftAssignmentViews:
    @pytest.mark.django_db
    def test_list_requires_view_permission(self, db):
        assert _client().get(reverse("aircraftassignment-list")).status_code == 403
        response = _client("view_aircraftassignment").get(
            reverse("aircraftassignment-list")
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_create_requires_add_permission(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        payload = {
            "aircraft": aircraft.pk,
            "cost_center": cc.pk,
            "start_date": TODAY.isoformat(),
            "status": "active",
            "purpose": "",
        }
        url = reverse("aircraftassignment-create")
        assert _client("view_aircraftassignment").post(url, payload).status_code == 403
        response = _client("add_aircraftassignment").post(url, payload)
        assert response.status_code == 302
        assert AircraftAssignment.objects.filter(
            aircraft=aircraft, cost_center=cc
        ).exists()


class TestResourceMovementLogView:
    @pytest.mark.django_db
    def test_requires_view_permission(self, db):
        op = _operator()
        OperatorAssignment.objects.create(
            operator=op, cost_center=_cc("CC1"), start_date=TODAY, status="active"
        )
        url = reverse("resourcemovementlog-list")
        assert _client().get(url).status_code == 403
        response = _client("view_resourcemovementlog").get(url)
        assert response.status_code == 200
        assert op.full_name in response.content.decode()

    @pytest.mark.django_db
    def test_filters_by_resource_kind(self, db):
        op = _operator()
        aircraft = Aircraft.objects.create(
            registration="CC-CCC", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc, start_date=TODAY, status="active"
        )
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc, start_date=TODAY, status="active"
        )
        client = _client("view_resourcemovementlog")

        response = client.get(
            reverse("resourcemovementlog-list"), {"resource_kind": "aircraft"}
        )

        content = response.content.decode()
        assert aircraft.registration in content
        assert op.full_name not in content
