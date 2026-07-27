"""OPS-4: FlightPermission as a DGAC-style mirror (roster + validity range)."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.registry.models import Aircraft, CostCenter, Operator

from .models import FlightPermission


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code)


def _operator(employee_id, cc):
    return Operator.objects.create(
        employee_id=employee_id, full_name=f"Pilot {employee_id}", cost_center=cc
    )


def _aircraft(registration, cc):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        cost_center=cc,
    )


class TestValidityRange:
    @pytest.mark.django_db
    def test_end_before_start_is_rejected(self, db):
        cc = _cc()
        permission = FlightPermission(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 22),
            valid_until=date(2026, 7, 20),
            location="Site",
        )
        with pytest.raises(ValidationError):
            permission.clean()

    @pytest.mark.django_db
    def test_equal_dates_are_a_single_day_permit(self, db):
        cc = _cc()
        permission = FlightPermission(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 22),
            valid_until=date(2026, 7, 22),
            location="Site",
        )
        permission.clean()  # must not raise


class TestRoster:
    @pytest.mark.django_db
    def test_permission_can_hold_several_operators_and_aircraft(self, db):
        cc = _cc()
        op1, op2 = _operator("E1", cc), _operator("E2", cc)
        ac1, ac2 = _aircraft("CC-A1", cc), _aircraft("CC-A2", cc)
        permission = FlightPermission.objects.create(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 10),
            location="Site",
        )
        permission.operators.set([op1, op2])
        permission.aircraft_fleet.set([ac1, ac2])

        assert permission.operators.count() == 2
        assert permission.aircraft_fleet.count() == 2
        assert op1 in permission.operators.all()
        assert ac2 in permission.aircraft_fleet.all()

    @pytest.mark.django_db
    def test_create_form_accepts_a_roster_via_checkboxes(self, db):
        cc = _cc()
        op1, op2 = _operator("E1", cc), _operator("E2", cc)
        ac1 = _aircraft("CC-A1", cc)
        client = _client("add_flightpermission")

        response = client.post(
            reverse("permission-create"),
            {
                "permission_number": "P-1",
                "operators": [op1.pk, op2.pk],
                "aircraft_fleet": [ac1.pk],
                "cost_center": cc.pk,
                "purpose": "Survey",
                "valid_from": "2026-07-01",
                "valid_until": "2026-07-10",
                "location": "Site",
            },
        )

        assert response.status_code == 302
        permission = FlightPermission.objects.get(permission_number="P-1")
        assert permission.operators.count() == 2
        assert permission.aircraft_fleet.get() == ac1


class TestCsvExportIncludesRoster:
    @pytest.mark.django_db
    def test_export_lists_operators_and_aircraft_as_joined_names(self, db):
        cc = _cc()
        op1, op2 = _operator("E1", cc), _operator("E2", cc)
        ac1 = _aircraft("CC-A1", cc)
        permission = FlightPermission.objects.create(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 10),
            location="Site",
        )
        permission.operators.set([op1, op2])
        permission.aircraft_fleet.set([ac1])
        client = _client("view_flightpermission")

        response = client.get(reverse("permission-list"), {"export": "csv"})

        content = b"".join(response.streaming_content).decode("utf-8-sig")
        assert op1.full_name in content
        assert op2.full_name in content
        assert ac1.registration in content


class TestCalendarSpansMultipleDays:
    @pytest.mark.django_db
    def test_json_feed_emits_start_and_end_for_the_full_range(self, db):
        cc = _cc()
        op = _operator("E1", cc)
        ac = _aircraft("CC-A1", cc)
        permission = FlightPermission.objects.create(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 5),
            valid_until=date(2026, 7, 8),
            location="Site",
        )
        permission.operators.add(op)
        permission.aircraft_fleet.add(ac)
        # A superuser, not a permission-scoped client: the JSON feed also scopes
        # by OperationalTenant membership, and a plain user with no tenant at
        # all would see zero events regardless of this test's subject -- that
        # tenant gate predates OPS-4 and is exercised by its own tests.
        User.objects.create_superuser("admin", "a@test.local", "pw")
        client = Client()
        assert client.login(username="admin", password="pw")

        response = client.get(
            reverse("calendar-events"),
            {"start": "2026-07-01", "end": "2026-08-01", "types": "permission"},
        )

        events = response.json()
        assert len(events) == 1
        assert events[0]["start"] == "2026-07-05"
        # FullCalendar's end is exclusive: a permit valid through the 8th ends
        # on the 9th so the 8th itself still renders as covered.
        assert events[0]["end"] == "2026-07-09"

    @pytest.mark.django_db
    def test_month_grid_places_the_permit_on_every_day_it_covers(self, db):
        cc = _cc()
        op = _operator("E1", cc)
        ac = _aircraft("CC-A1", cc)
        permission = FlightPermission.objects.create(
            permission_number="P-1",
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 5),
            valid_until=date(2026, 7, 8),
            location="Site",
        )
        permission.operators.add(op)
        permission.aircraft_fleet.add(ac)
        client = _client("view_flightpermission")

        response = client.get(reverse("ops-calendar"), {"month": "2026-07"})

        events = response.context["events"]
        covered_days = {day.day for day, entries in events.items() if entries}
        assert {5, 6, 7, 8}.issubset(covered_days)
