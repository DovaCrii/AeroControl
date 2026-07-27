from datetime import date

import pytest
from django.test import Client
from django.utils import translation
from django.urls import reverse

from apps.core.models import OperationalTenant
from apps.operations.models import FlightPermission
from apps.registry.forms import AssignmentForm
from apps.registry.models import (
    Aircraft,
    Assignment,
    CostCenter,
    Operator,
    Qualification,
)


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="registry-admin", email="registry@example.com", password="password"
    )


@pytest.fixture
def registry_data():
    tenant = OperationalTenant.objects.create(name="Operations", slug="operations")
    center = CostCenter.objects.create(code="410", name="Operations", tenant=tenant)
    operator = Operator.objects.create(
        employee_id="OP-1", full_name="Pilot One", tenant=tenant, cost_center=center
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPAS",
        model="Mavic 3",
        manufacturer="DJI",
        tenant=tenant,
        cost_center=center,
    )
    return tenant, center, operator, aircraft


@pytest.mark.django_db
def test_aircraft_list_exposes_model(client, admin_user, registry_data):
    client.force_login(admin_user)
    response = client.get(reverse("aircraft-list"))

    assert response.status_code == 200
    assert "RPA-1" in response.content.decode()
    assert "Mavic 3" in response.content.decode()


@pytest.mark.django_db
def test_confirmed_assignment_rejects_operator_overlap(registry_data):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 12),
        status="confirmed",
    )
    form = AssignmentForm(
        data={
            "operator": operator.pk,
            "aircraft": aircraft.pk,
            "cost_center": center.pk,
            "purpose": "Inspection",
            "start_date": "2026-07-11",
            "end_date": "2026-07-13",
            "status": "confirmed",
        }
    )

    assert not form.is_valid()
    assert "operator" in form.errors


@pytest.mark.django_db
def test_assignment_status_choices_are_translated_and_confirmed_requires_cost_center(
    registry_data,
):
    _tenant, _center, operator, aircraft = registry_data
    with translation.override("es"):
        form = AssignmentForm()
        assert dict(form.fields["status"].choices)["planned"] == "Planificado"

    form = AssignmentForm(
        data={
            "operator": operator.pk,
            "aircraft": aircraft.pk,
            "cost_center": "",
            "purpose": "Inspection",
            "start_date": "2026-07-11",
            "end_date": "2026-07-13",
            "status": "confirmed",
        }
    )

    assert not form.is_valid()
    assert "cost_center" in form.errors


@pytest.mark.django_db
def test_assignment_list_filters_by_status_and_review(
    client, admin_user, registry_data
):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 10),
        status="confirmed",
    )
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        start_date=date(2026, 7, 20),
        status="planned",
    )
    client.force_login(admin_user)

    response = client.get(reverse("assignment-list"), {"status": "confirmed"})
    assert response.status_code == 200
    assert response.context["object_list"].count() == 1
    assert "Período" in response.content.decode()

    response = client.get(reverse("assignment-list"), {"review": "needs_review"})
    assert response.context["object_list"].count() == 1


@pytest.mark.django_db
def test_calendar_feed_contains_resource_and_expiration_events(
    client, admin_user, registry_data
):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        status="planned",
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type="RPAS",
        issue_date=date(2026, 1, 1),
        expiry_date=date(2026, 7, 21),
    )
    FlightPermission.objects.create(
        permission_number="PERM-1",
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        purpose="Inspection",
        flight_date=date(2026, 7, 20),
        location="Santiago",
    )
    client.force_login(admin_user)

    response = client.get(
        reverse("calendar-events"),
        {
            "start": "2026-07-01",
            "end": "2026-08-01",
            "types": "permission,assignment,qualification",
        },
    )
    event_types = {event["type"] for event in response.json()}

    assert response.status_code == 200
    assert {"permission", "assignment", "qualification"}.issubset(event_types)


class TestArchiveRestoreFromUI:
    """V.30/V.31: archiving lived only in the technical admin, and archiving a
    cost center silently dropped it from the digest."""

    @staticmethod
    def _world(db):
        center = CostCenter.objects.create(code="ARC", name="Archive tests")
        operator = Operator.objects.create(
            employee_id="ARC-1", full_name="Pilot", cost_center=center,
            email="pilot@test.cl",
        )
        return center, operator

    @staticmethod
    def _client(*codenames):
        from django.contrib.auth.models import Permission, User

        user = User.objects.create_user(f"u-{'-'.join(codenames)}", password="pw")
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=codenames)
        )
        client = Client()
        assert client.login(username=user.username, password="pw")
        return client

    @pytest.mark.django_db
    def test_archive_requires_delete_permission(self, db):
        _, operator = self._world(db)
        client = self._client("view_operator", "change_operator")

        response = client.post(reverse("operator-archive", args=[operator.pk]))

        operator.refresh_from_db()
        assert response.status_code == 403
        assert operator.is_active is True

    @pytest.mark.django_db
    def test_archive_and_restore_roundtrip(self, db):
        _, operator = self._world(db)
        client = self._client("delete_operator", "change_operator")

        archived = client.post(reverse("operator-archive", args=[operator.pk]))
        operator.refresh_from_db()
        assert archived.status_code == 302
        assert operator.is_active is False

        restored = client.post(reverse("operator-restore", args=[operator.pk]))
        operator.refresh_from_db()
        assert restored.status_code == 302
        assert operator.is_active is True

    @pytest.mark.django_db
    def test_cost_center_archive_shows_dependents_first(self, db):
        center, operator = self._world(db)
        client = self._client("delete_costcenter")

        response = client.post(reverse("costcenter-archive", args=[center.pk]))

        center.refresh_from_db()
        assert response.status_code == 200  # confirmation page, nothing archived
        assert center.is_active is True
        assert "1" in response.content.decode()

        confirmed = client.post(
            reverse("costcenter-archive", args=[center.pk]), {"confirm": "1"}
        )
        center.refresh_from_db()
        assert confirmed.status_code == 302
        assert center.is_active is False

    @pytest.mark.django_db
    def test_cost_center_without_dependents_archives_directly(self, db):
        center = CostCenter.objects.create(code="EMPTY", name="No dependents")
        client = self._client("delete_costcenter")

        response = client.post(reverse("costcenter-archive", args=[center.pk]))

        center.refresh_from_db()
        assert response.status_code == 302
        assert center.is_active is False

    @pytest.mark.django_db
    def test_notification_email_ignores_archived_operator(self, db):
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.save(update_fields=["responsible_operator"])
        assert center.notification_email == "pilot@test.cl"

        operator.is_active = False
        operator.save(update_fields=["is_active"])

        assert center.notification_email == ""

    @pytest.mark.django_db
    def test_notification_email_falls_back_to_external_contact(self, db):
        """The responsible person is not always in the operator roster (an
        administrator, secretary, or safety officer instead of a pilot)."""
        center, _ = self._world(db)
        center.responsible_contact_name = "Secretaria de faena"
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(
            update_fields=["responsible_contact_name", "responsible_contact_email"]
        )

        assert center.notification_email == "secretaria@test.cl"

    @pytest.mark.django_db
    def test_notification_email_prefers_operator_over_external_contact(self, db):
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(
            update_fields=["responsible_operator", "responsible_contact_email"]
        )

        assert center.notification_email == "pilot@test.cl"

    @pytest.mark.django_db
    def test_notification_email_falls_back_to_contact_when_operator_unreachable(
        self, db
    ):
        """An operator on file who left is not a reason to go silent when an
        external contact is also configured."""
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(
            update_fields=["responsible_operator", "responsible_contact_email"]
        )
        operator.is_active = False
        operator.save(update_fields=["is_active"])

        assert center.notification_email == "secretaria@test.cl"

    @pytest.mark.django_db
    def test_digest_reports_archived_center_with_active_dependents(self, db):
        from apps.compliance.digest import archived_centers_with_active_dependents

        center, operator = self._world(db)
        center.is_active = False
        center.save(update_fields=["is_active"])

        rows = archived_centers_with_active_dependents()

        assert len(rows) == 1
        reported, operators, aircraft = rows[0]
        assert reported.pk == center.pk
        assert operators == 1
        assert aircraft == 0
