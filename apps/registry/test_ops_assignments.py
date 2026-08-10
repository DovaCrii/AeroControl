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
        # LV-18: the "+ New" entry point is now the bulk-assign form.
        op = _operator()
        cc = _cc("CC1")
        payload = {
            "cost_center": cc.pk,
            "operators": [op.pk],
            "status": "active",
            "purpose": "",
        }
        url = reverse("operatorassignment-create")
        assert _client("view_operatorassignment").post(url, payload).status_code == 403

        response = _client("add_operatorassignment").post(url, payload)
        assert response.status_code == 302
        assert OperatorAssignment.objects.filter(operator=op, cost_center=cc).exists()

    @pytest.mark.django_db
    def test_create_assigns_several_operators_at_once(self, db):
        # LV-18: 5-10 operators onto a contract in one submit, not one by one.
        ops = [_operator(employee_id=f"E{i}", full_name=f"Pilot {i}") for i in range(3)]
        cc = _cc("CC1")
        payload = {
            "cost_center": cc.pk,
            "operators": [o.pk for o in ops],
            "status": "active",
            "purpose": "",
        }
        response = _client("add_operatorassignment").post(
            reverse("operatorassignment-create"), payload, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 204
        assert response.headers.get("HX-Trigger") == "modal-form-success"
        assert OperatorAssignment.objects.filter(cost_center=cc).count() == 3
        for operator in ops:
            operator.refresh_from_db()
            assert operator.cost_center_id == cc.pk

    @pytest.mark.django_db
    def test_bulk_reassign_moves_instead_of_rejecting(self, db):
        # LV-17/18: with an operator already placed, bulk-assigning them to a new
        # cost center moves them (ends the old, opens the new) rather than
        # hitting the per-operator overlap guard the single form used to raise.
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        payload = {
            "cost_center": cc2.pk,
            "operators": [op.pk],
            "status": "active",
            "purpose": "",
        }
        response = _client("add_operatorassignment").post(
            reverse("operatorassignment-create"), payload, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 204
        op.refresh_from_db()
        assert op.cost_center_id == cc2.pk
        assert OperatorAssignment.objects.filter(
            operator=op, cost_center=cc1, status="ended"
        ).exists()
        assert OperatorAssignment.objects.filter(
            operator=op, cost_center=cc2, status="active"
        ).exists()


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
        # R5.6: the "+ New" entry point is now the bulk-assign form (same
        # move OperatorAssignment made for LV-18) -- one aircraft is just
        # the smallest case of "one or more".
        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        payload = {
            "aircraft": [aircraft.pk],
            "cost_center": cc.pk,
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

    @pytest.mark.django_db
    def test_create_assigns_several_aircraft_at_once(self, db):
        aircraft_fleet = [
            Aircraft.objects.create(
                registration=f"CC-{i}", type="RPA", model="M3", manufacturer="DJI"
            )
            for i in range(3)
        ]
        cc = _cc("CC1")
        payload = {
            "cost_center": cc.pk,
            "aircraft": [a.pk for a in aircraft_fleet],
            "status": "active",
            "purpose": "",
        }
        response = _client("add_aircraftassignment").post(
            reverse("aircraftassignment-create"), payload, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 204
        assert response.headers.get("HX-Trigger") == "modal-form-success"
        assert AircraftAssignment.objects.filter(cost_center=cc).count() == 3
        for aircraft in aircraft_fleet:
            aircraft.refresh_from_db()
            assert aircraft.cost_center_id == cc.pk

    @pytest.mark.django_db
    def test_bulk_reassign_moves_instead_of_rejecting(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc1, start_date=TODAY, status="active"
        )
        payload = {
            "cost_center": cc2.pk,
            "aircraft": [aircraft.pk],
            "status": "active",
            "purpose": "",
        }
        response = _client("add_aircraftassignment").post(
            reverse("aircraftassignment-create"), payload, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 204
        aircraft.refresh_from_db()
        assert aircraft.cost_center_id == cc2.pk
        assert AircraftAssignment.objects.filter(
            aircraft=aircraft, cost_center=cc1, status="ended"
        ).exists()
        assert AircraftAssignment.objects.filter(
            aircraft=aircraft, cost_center=cc2, status="active"
        ).exists()


class TestMovementAttribution:
    """R5.2 [bug]: a ResourceMovementLog row without an author is not useful
    as evidence. Only bulk_assign_operators (services.py) was setting
    `_changed_by_user` -- every plain CRUD save through RegistryCreate/
    RegistryUpdate left it blank, so creating an AircraftAssignment or
    editing an OperatorAssignment through the ordinary form logged a
    movement with no one attached to it."""

    @pytest.mark.django_db
    def test_creating_an_aircraft_assignment_via_the_view_attributes_the_user(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-DDD", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        user = User.objects.create_user("creator", password="pw")
        user.user_permissions.add(
            Permission.objects.get(codename="add_aircraftassignment")
        )
        client = Client()
        assert client.login(username="creator", password="pw")

        client.post(
            reverse("aircraftassignment-create"),
            {
                "aircraft": aircraft.pk,
                "cost_center": cc.pk,
                "start_date": TODAY.isoformat(),
                "status": "active",
                "purpose": "",
            },
        )

        log = ResourceMovementLog.objects.get(resource_id=aircraft.pk)
        assert log.changed_by_user_id == user.pk

    @pytest.mark.django_db
    def test_editing_an_operator_assignment_via_the_view_attributes_the_user(self, db):
        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        assignment = OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        user = User.objects.create_user("editor", password="pw")
        user.user_permissions.add(
            Permission.objects.get(codename="change_operatorassignment")
        )
        client = Client()
        assert client.login(username="editor", password="pw")

        client.post(
            reverse("operatorassignment-update", args=[assignment.pk]),
            {
                "operator": op.pk,
                "cost_center": cc2.pk,
                "status": "active",
                "purpose": "",
            },
        )

        log = ResourceMovementLog.objects.filter(resource_id=op.pk).latest("sequence")
        assert log.movement == "reassigned"
        assert log.changed_by_user_id == user.pk


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

    @pytest.mark.django_db
    def test_detail_column_renders(self, db):
        """R5.3: `detail` exists on the model (e.g. OPS-3's location-change
        text) but the list did not render it."""
        aircraft = Aircraft.objects.create(
            registration="CC-EEE", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        aircraft.current_location = "on_site"
        aircraft.current_site = cc
        aircraft.save(update_fields=["current_location", "current_site", "updated_at"])

        response = _client("view_resourcemovementlog").get(
            reverse("resourcemovementlog-list")
        )

        content = response.content.decode()
        assert "Casa matriz" in content  # from_location -> to_location text
        assert "En faena" in content

    @pytest.mark.django_db
    def test_search_matches_the_aircrafts_registration(self, db):
        # R5.3: resource_id is a bare UUID, not a join -- search resolves the
        # matching Aircraft/Operator ids first, same as the tenant scoping.
        op = _operator()
        aircraft = Aircraft.objects.create(
            registration="RPA-4647", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc, start_date=TODAY, status="active"
        )
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc, start_date=TODAY, status="active"
        )
        client = _client("view_resourcemovementlog")

        response = client.get(reverse("resourcemovementlog-list"), {"q": "4647"})

        content = response.content.decode()
        assert aircraft.registration in content
        assert op.full_name not in content

    @pytest.mark.django_db
    def test_search_matches_the_detail_text(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-FFF", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        aircraft.current_location = "on_site"
        aircraft.current_site = cc
        aircraft.save(update_fields=["current_location", "current_site", "updated_at"])
        other = Aircraft.objects.create(
            registration="CC-GGG", type="RPA", model="M3", manufacturer="DJI"
        )
        AircraftAssignment.objects.create(
            aircraft=other, cost_center=cc, start_date=TODAY, status="active"
        )
        client = _client("view_resourcemovementlog")

        response = client.get(reverse("resourcemovementlog-list"), {"q": "En faena"})

        content = response.content.decode()
        assert aircraft.registration in content
        assert other.registration not in content

    @pytest.mark.django_db
    def test_export_csv(self, db):
        op = _operator()
        OperatorAssignment.objects.create(
            operator=op, cost_center=_cc("CC1"), start_date=TODAY, status="active"
        )
        client = _client("view_resourcemovementlog")

        response = client.get(reverse("resourcemovementlog-list"), {"export": "csv"})

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        body = b"".join(response.streaming_content).decode()
        assert "assigned" in body


class TestBulkAssignService:
    @pytest.mark.django_db
    def test_assigns_many_operators_and_returns_count(self, db):
        from apps.registry.services import bulk_assign_operators

        ops = [_operator(employee_id=f"E{i}", full_name=f"P{i}") for i in range(3)]
        cc = _cc("CC1")
        moved = bulk_assign_operators(
            operators=ops,
            cost_center=cc,
            status="active",
            purpose="",
            purpose_detail="",
            user=None,
        )
        assert moved == 3
        assert (
            OperatorAssignment.objects.filter(cost_center=cc, status="active").count()
            == 3
        )
        for operator in ops:
            operator.refresh_from_db()
            assert operator.cost_center_id == cc.pk

    @pytest.mark.django_db
    def test_operator_already_on_target_is_skipped(self, db):
        from apps.registry.services import bulk_assign_operators

        op = _operator()
        cc = _cc("CC1")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc, start_date=TODAY, status="active"
        )
        moved = bulk_assign_operators(
            operators=[op],
            cost_center=cc,
            status="active",
            purpose="",
            purpose_detail="",
            user=None,
        )
        assert moved == 0
        assert (
            OperatorAssignment.objects.filter(operator=op, cost_center=cc).count() == 1
        )

    @pytest.mark.django_db
    def test_moving_an_operator_ends_the_old_and_logs_reassigned(self, db):
        from apps.registry.services import bulk_assign_operators

        op = _operator()
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        OperatorAssignment.objects.create(
            operator=op, cost_center=cc1, start_date=TODAY, status="active"
        )
        user = User.objects.create_user("mover", password="pw")
        moved = bulk_assign_operators(
            operators=[op],
            cost_center=cc2,
            status="active",
            purpose="",
            purpose_detail="",
            user=user,
        )
        assert moved == 1
        op.refresh_from_db()
        assert op.cost_center_id == cc2.pk
        assert OperatorAssignment.objects.filter(
            operator=op, cost_center=cc1, status="ended"
        ).exists()
        latest = ResourceMovementLog.objects.filter(resource_id=op.pk).first()
        assert latest.movement == "reassigned"
        assert latest.from_cost_center_id == cc1.pk
        assert latest.to_cost_center_id == cc2.pk
        assert latest.changed_by_user_id == user.pk


class TestBulkAssignAircraftService:
    """R5.6: same bulk-move service as TestBulkAssignService above, for
    aircraft -- see apps.registry.services.bulk_assign_aircraft."""

    @pytest.mark.django_db
    def test_assigns_many_aircraft_and_returns_count(self, db):
        from apps.registry.services import bulk_assign_aircraft

        fleet = [
            Aircraft.objects.create(
                registration=f"CC-{i}", type="RPA", model="M3", manufacturer="DJI"
            )
            for i in range(3)
        ]
        cc = _cc("CC1")
        moved = bulk_assign_aircraft(
            aircraft=fleet,
            cost_center=cc,
            status="active",
            purpose="",
            purpose_detail="",
            user=None,
        )
        assert moved == 3
        assert (
            AircraftAssignment.objects.filter(cost_center=cc, status="active").count()
            == 3
        )
        for aircraft in fleet:
            aircraft.refresh_from_db()
            assert aircraft.cost_center_id == cc.pk

    @pytest.mark.django_db
    def test_aircraft_already_on_target_is_skipped(self, db):
        from apps.registry.services import bulk_assign_aircraft

        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )
        cc = _cc("CC1")
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc, start_date=TODAY, status="active"
        )
        moved = bulk_assign_aircraft(
            aircraft=[aircraft],
            cost_center=cc,
            status="active",
            purpose="",
            purpose_detail="",
            user=None,
        )
        assert moved == 0
        assert (
            AircraftAssignment.objects.filter(aircraft=aircraft, cost_center=cc).count()
            == 1
        )

    @pytest.mark.django_db
    def test_moving_an_aircraft_ends_the_old_and_logs_reassigned(self, db):
        from apps.registry.services import bulk_assign_aircraft

        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )
        cc1, cc2 = _cc("CC1"), _cc("CC2")
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc1, start_date=TODAY, status="active"
        )
        user = User.objects.create_user("mover2", password="pw")
        moved = bulk_assign_aircraft(
            aircraft=[aircraft],
            cost_center=cc2,
            status="active",
            purpose="",
            purpose_detail="",
            user=user,
        )
        assert moved == 1
        aircraft.refresh_from_db()
        assert aircraft.cost_center_id == cc2.pk
        assert AircraftAssignment.objects.filter(
            aircraft=aircraft, cost_center=cc1, status="ended"
        ).exists()
        latest = ResourceMovementLog.objects.filter(resource_id=aircraft.pk).first()
        assert latest.movement == "reassigned"
        assert latest.from_cost_center_id == cc1.pk
        assert latest.to_cost_center_id == cc2.pk
        assert latest.changed_by_user_id == user.pk


class TestOperatorAssignmentFormLV17:
    @pytest.mark.django_db
    def test_form_drops_the_date_fields(self, db):
        from apps.registry.forms import OperatorAssignmentForm

        fields = OperatorAssignmentForm().fields
        assert "start_date" not in fields
        assert "end_date" not in fields

    @pytest.mark.django_db
    def test_save_autofills_start_date_with_today(self, db):
        from apps.registry.forms import OperatorAssignmentForm

        op = _operator()
        cc = _cc("CC1")
        form = OperatorAssignmentForm(
            data={
                "operator": op.pk,
                "cost_center": cc.pk,
                "status": "active",
                "purpose": "",
            }
        )
        assert form.is_valid(), form.errors
        instance = form.save()
        assert instance.start_date == TODAY
