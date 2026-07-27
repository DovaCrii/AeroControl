"""OPS-1: per-resource assignments, the denormalization signal and the log."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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
