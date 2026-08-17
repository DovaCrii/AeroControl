"""R7.5: daily flight duty limit (ISO 45001 6.1.2 / 8.1.2).

Pilot fatigue is a hazard the field IPER must control, and the duty limit is
the control the audit guide names. Nothing new is stored: FlightRecord already
had date, departure, arrival and pilot, so this is an aggregate over what the
operation already writes down.
"""

from datetime import date, time, timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from apps.core.testing import login_as
from apps.core.groups import REPORT_RECIPIENTS
from apps.operations.models import FlightPermission, FlightRecord
from apps.operations.selectors import (
    DAILY_FLIGHT_LIMIT,
    duty_time_for,
    pilots_over_daily_limit,
)
from apps.registry.models import Aircraft, CostCenter, Operator

DAY = date(2026, 8, 20)


@pytest.fixture
def setup(db):
    cost_center = CostCenter.objects.create(code="CC1", name="Uno")
    pilot = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
    )
    permission = FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=DAY,
        valid_until=DAY + timedelta(days=5),
        location="Faena Norte",
        area_type="unpopulated",
    )
    permission.operators.add(pilot)
    permission.aircraft_fleet.add(aircraft)
    return permission, pilot, aircraft


def _flight(permission, pilot, aircraft, departure, arrival, day=DAY):
    return FlightRecord.objects.create(
        permission=permission,
        actual_date=day,
        departure_time=departure,
        arrival_time=arrival,
        pilot=pilot,
        aircraft=aircraft,
    )


class TestTheAggregate:
    @pytest.mark.django_db
    def test_sums_every_flight_the_pilot_logged_that_day(self, setup):
        permission, pilot, aircraft = setup
        _flight(permission, pilot, aircraft, time(8, 0), time(11, 0))
        _flight(permission, pilot, aircraft, time(13, 0), time(15, 30))

        assert duty_time_for(pilot, DAY) == timedelta(hours=5, minutes=30)

    @pytest.mark.django_db
    def test_ignores_other_days(self, setup):
        permission, pilot, aircraft = setup
        _flight(permission, pilot, aircraft, time(8, 0), time(11, 0))
        _flight(
            permission,
            pilot,
            aircraft,
            time(8, 0),
            time(12, 0),
            day=DAY + timedelta(days=1),
        )

        assert duty_time_for(pilot, DAY) == timedelta(hours=3)

    @pytest.mark.django_db
    def test_ignores_archived_records(self, setup):
        """FlightRecordDelete archives rather than deletes; an archived flight
        must not keep counting against a pilot's day."""
        permission, pilot, aircraft = setup
        record = _flight(permission, pilot, aircraft, time(8, 0), time(11, 0))
        record.is_active = False
        record.save(update_fields=["is_active"])

        assert duty_time_for(pilot, DAY) == timedelta()

    @pytest.mark.django_db
    def test_exactly_at_the_limit_is_not_over_it(self, setup):
        """The limit is what is allowed, not the first value disallowed."""
        permission, pilot, aircraft = setup
        _flight(permission, pilot, aircraft, time(6, 0), time(14, 0))  # 8h

        assert duty_time_for(pilot, DAY) == DAILY_FLIGHT_LIMIT
        assert pilots_over_daily_limit(DAY) == []

    @pytest.mark.django_db
    def test_lists_only_the_pilots_past_the_limit(self, setup):
        permission, pilot, aircraft = setup
        other = Operator.objects.create(employee_id="P2", full_name="Pilot Two")
        permission.operators.add(other)
        _flight(permission, pilot, aircraft, time(6, 0), time(14, 30))  # 8h30
        _flight(permission, other, aircraft, time(9, 0), time(10, 0))  # 1h

        over = pilots_over_daily_limit(DAY)

        assert [pair[0] for pair in over] == [pilot]
        assert over[0][1] == timedelta(hours=8, minutes=30)


class TestTheWarningOnSaving:
    @pytest.mark.django_db
    def test_saves_the_flight_and_warns(self, setup):
        """A warning, never a rejection: the record is written after the
        flight, so refusing it would not un-fly the day -- it would only leave
        the excess unrecorded, losing the evidence the clause exists for."""
        permission, pilot, aircraft = setup
        _flight(permission, pilot, aircraft, time(6, 0), time(13, 0))  # 7h already
        client = login_as("add_flightrecord", "view_flightrecord")

        response = client.post(
            reverse("record-create"),
            {
                "permission": permission.pk,
                "actual_date": DAY.isoformat(),
                "departure_time": "14:00",
                "arrival_time": "16:00",  # +2h -> 9h total
                "pilot": pilot.pk,
                "aircraft": aircraft.pk,
            },
            follow=True,
        )

        assert FlightRecord.objects.count() == 2
        messages = [str(m) for m in response.context["messages"]]
        assert any("9h 00min" in message for message in messages)
        assert any("8h 00min" in message for message in messages)

    @pytest.mark.django_db
    def test_no_warning_under_the_limit(self, setup):
        permission, pilot, aircraft = setup
        client = login_as("add_flightrecord", "view_flightrecord")

        response = client.post(
            reverse("record-create"),
            {
                "permission": permission.pk,
                "actual_date": DAY.isoformat(),
                "departure_time": "09:00",
                "arrival_time": "11:00",
                "pilot": pilot.pk,
                "aircraft": aircraft.pk,
            },
            follow=True,
        )

        assert FlightRecord.objects.count() == 1
        messages = [str(m) for m in response.context["messages"]]
        assert not any("daily flight limit" in message for message in messages)


class TestTheScheduledJob:
    def _recipients(self):
        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)

    @pytest.mark.django_db
    def test_reports_the_pilots_over_the_limit(self, setup):
        permission, pilot, aircraft = setup
        self._recipients()
        _flight(permission, pilot, aircraft, time(6, 0), time(15, 0))  # 9h

        call_command("check_flight_duty_limit", "--date", DAY.isoformat())

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "Pilot One" in body
        assert "9h 00min" in body
        # And by how much, which is what makes it actionable.
        assert "1h 00min" in body

    @pytest.mark.django_db
    def test_says_nothing_when_everyone_is_within_the_limit(self, setup):
        permission, pilot, aircraft = setup
        self._recipients()
        _flight(permission, pilot, aircraft, time(9, 0), time(11, 0))

        call_command("check_flight_duty_limit", "--date", DAY.isoformat())

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_defaults_to_yesterday(self, setup):
        """A day is only complete once it is over: run at 08:00 on the day
        itself it would report a partial total and read like an all-clear."""
        from django.utils import timezone

        permission, pilot, aircraft = setup
        self._recipients()
        yesterday = timezone.localdate() - timedelta(days=1)
        _flight(permission, pilot, aircraft, time(6, 0), time(15, 0), day=yesterday)

        call_command("check_flight_duty_limit")

        assert len(mail.outbox) == 1
        assert "Pilot One" in mail.outbox[0].body

    @pytest.mark.django_db
    def test_never_touches_the_records(self, setup):
        permission, pilot, aircraft = setup
        self._recipients()
        record = _flight(permission, pilot, aircraft, time(6, 0), time(15, 0))

        call_command("check_flight_duty_limit", "--date", DAY.isoformat())

        record.refresh_from_db()
        assert record.is_active is True
        assert FlightRecord.objects.count() == 1

    @pytest.mark.django_db
    def test_dry_run_sends_nothing(self, setup):
        permission, pilot, aircraft = setup
        self._recipients()
        _flight(permission, pilot, aircraft, time(6, 0), time(15, 0))

        call_command("check_flight_duty_limit", "--date", DAY.isoformat(), "--dry-run")

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_missing_recipients_group_does_not_crash_the_timer(self, setup):
        permission, pilot, aircraft = setup
        _flight(permission, pilot, aircraft, time(6, 0), time(15, 0))

        call_command("check_flight_duty_limit", "--date", DAY.isoformat())

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_rejects_a_malformed_date(self, setup):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("check_flight_duty_limit", "--date", "20-08-2026")
