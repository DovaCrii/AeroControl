"""LV-458 (B7, Manual Act. 19, Anexo D, D-3 §I): la regla de inactividad.

Seis meses sin volar exigen el repaso (cuestionario anual del RPA que se va a
operar); dos años, repetir el examen general y el de limitaciones. Va **apagada**
(`INACTIVITY_RULE_ENABLED`): apagada no cambia nada; encendida, cada pata se
prueba variando una a la vez. Sin vuelos en la bitácora sólo avisa.
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.testing import login_as
from apps.operations.models import FlightPermission, FlightRecord
from apps.operations.readiness import _check_operator
from apps.registry.assessment_testing import make_family
from apps.registry.assessments import add_months
from apps.registry.models import Aircraft, CostCenter, KnowledgeAssessment, Operator
from apps.registry.recency import recency

TODAY = date(2026, 11, 23)
LABEL = gettext("Inactivity review")


@pytest.fixture
def world(db):
    centre = CostCenter.objects.create(code="CC738", name="MLP")
    operator = Operator.objects.create(
        employee_id="E1",
        full_name="Operator A",
        cost_center=centre,
        credential_expiry=TODAY + timedelta(days=300),
    )
    mavic = make_family()
    matrice = make_family("matrice", "Matrice series", "matrice")
    aircraft = Aircraft.objects.create(
        registration="RPA-1", model="Mavic 3 Enterprise", cost_center=centre
    )
    permit = FlightPermission.objects.create(
        internal_folio="F-1",
        cost_center=centre,
        purpose="patrol",
        valid_from=date(2024, 1, 1),
        valid_until=date(2027, 12, 31),
        location="x",
        area_type="unpopulated",
        status=FlightPermission.STATUS_APPROVED,
    )
    return {
        "operator": operator,
        "aircraft": aircraft,
        "mavic": mavic,
        "matrice": matrice,
        "permit": permit,
    }


def _flight(world, day, **extra):
    return FlightRecord.objects.create(
        permission=world["permit"],
        actual_date=day,
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
        pilot=world["operator"],
        aircraft=world["aircraft"],
        **extra,
    )


def _attempt(world, kind, taken_on, *, passed=True, family="same"):
    family = world["mavic"] if family == "same" else family
    row = KnowledgeAssessment.objects.create(
        operator=world["operator"],
        kind=kind,
        aircraft_family=family if kind in ("annual", "limitations") else None,
        question_count=20,
        correct_count=20 if passed else 5,
        score_percent=100 if passed else 25,
        passed=passed,
    )
    KnowledgeAssessment.objects.filter(pk=row.pk).update(
        taken_at=datetime.combine(taken_on, time(12, 0)).replace(tzinfo=dt_timezone.utc)
    )
    return row


def _check(world):
    return _check_operator(world["operator"], TODAY, world["aircraft"])


def _mine(items):
    return [item for item in items if str(item.label) == str(LABEL)]


@pytest.mark.django_db
class TestOff:
    def test_off_is_exactly_the_baseline(self, world, settings):
        settings.INACTIVITY_RULE_ENABLED = False
        baseline = _check(world)
        _flight(world, date(2025, 1, 10))  # más de un año sin volar

        check = _check(world)

        assert not _mine(check.blockers) and not _mine(check.warnings)
        assert [str(i.detail) for i in check.blockers] == [
            str(i.detail) for i in baseline.blockers
        ]
        assert [str(i.detail) for i in check.warnings] == [
            str(i.detail) for i in baseline.warnings
        ]

    def test_off_the_sheet_has_no_line_and_no_extra_queries(self, world, settings):
        _flight(world, date(2025, 1, 10))
        client = login_as("view_operator")
        url = reverse("operator-detail", args=[world["operator"].pk])

        settings.INACTIVITY_RULE_ENABLED = False
        with CaptureQueriesContext(connection) as off:
            response = client.get(url)
        assert response.status_code == 200
        assert "inactivity" not in response.context
        assert gettext("Last recorded flight") not in response.content.decode()

        settings.INACTIVITY_RULE_ENABLED = True
        with CaptureQueriesContext(connection) as on:
            response = client.get(url)
        assert gettext("Last recorded flight") in response.content.decode()
        assert len(on) > len(off)


@pytest.fixture
def on(settings):
    settings.INACTIVITY_RULE_ENABLED = True


@pytest.mark.django_db
@pytest.mark.usefixtures("on")
class TestOn:
    def test_six_months_and_a_day_blocks(self, world):
        _flight(world, date(2026, 5, 22))

        check = _check(world)

        assert len(_mine(check.blockers)) == 1
        assert "22-05-2026" in str(_mine(check.blockers)[0].detail)

    def test_the_last_day_still_warns_instead_of_blocking(self, world):
        _flight(world, date(2026, 5, 24))

        check = _check(world)

        assert not _mine(check.blockers)
        assert len(_mine(check.warnings)) == 1

    def test_a_recent_flight_is_silent(self, world):
        _flight(world, date(2026, 10, 1))

        check = _check(world)

        assert not _mine(check.blockers) and not _mine(check.warnings)

    def test_the_month_end_boundary(self, world):
        assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
        _flight(world, date(2026, 8, 31))
        result = recency(world["operator"], date(2027, 2, 28), world["aircraft"])
        assert result.due_on == date(2027, 2, 28)
        assert result.state == "due_soon"
        assert recency(world["operator"], date(2027, 3, 1)).state == "inactive"

    def test_an_annual_of_the_same_model_after_the_flight_unblocks(self, world):
        _flight(world, date(2026, 5, 1))
        _attempt(world, "annual", date(2026, 11, 1))

        check = _check(world)

        assert not _mine(check.blockers)

    def test_another_model_does_not_count(self, world):
        _flight(world, date(2026, 5, 1))
        _attempt(world, "annual", date(2026, 11, 1), family=world["matrice"])

        assert len(_mine(_check(world).blockers)) == 1

    def test_a_failed_attempt_does_not_count(self, world):
        _flight(world, date(2026, 5, 1))
        _attempt(world, "annual", date(2026, 11, 1), passed=False)

        assert len(_mine(_check(world).blockers)) == 1

    def test_a_legacy_pass_does_not_count(self, world):
        _flight(world, date(2026, 5, 1))
        _attempt(world, "legacy", date(2026, 11, 1))

        assert len(_mine(_check(world).blockers)) == 1

    def test_no_flight_at_all_only_warns(self, world):
        check = _check(world)

        assert not _mine(check.blockers)
        assert len(_mine(check.warnings)) == 1
        assert str(_mine(check.warnings)[0].detail) == gettext(
            "No flight on record in the digital logbook, so inactivity "
            "cannot be checked."
        )

    def test_no_flight_with_attempts_only_warns(self, world):
        _attempt(world, "annual", date(2026, 11, 1))

        check = _check(world)

        assert not _mine(check.blockers)
        assert len(_mine(check.warnings)) == 1

    def test_two_years_blocks_until_general_and_limitations_follow(self, world):
        _flight(world, date(2024, 11, 1))
        _attempt(world, "annual", date(2026, 11, 1))
        blockers = _mine(_check(world).blockers)
        assert len(blockers) == 1
        assert str(blockers[0].detail) == gettext(
            "More than two years without flying: repeat the general exam "
            "and the limitations exam."
        )
        assert recency(world["operator"], TODAY, world["aircraft"]).needs == (
            "general",
            "limitations",
        )

        _attempt(world, "general", date(2026, 11, 2))
        assert _mine(_check(world).blockers)  # falta limitaciones

        _attempt(world, "limitations", date(2026, 11, 2))
        assert not _mine(_check(world).blockers)

    def test_an_exam_before_the_last_flight_does_not_count_for_retraining(self, world):
        _attempt(world, "general", date(2024, 1, 1))
        _attempt(world, "limitations", date(2024, 1, 1))
        _flight(world, date(2024, 11, 1))

        assert _mine(_check(world).blockers)

    def test_an_archived_flight_does_not_count(self, world):
        _flight(world, date(2026, 10, 1), is_active=False)
        _flight(world, date(2026, 5, 1))

        result = recency(world["operator"], TODAY, world["aircraft"])

        assert result.last_flight == date(2026, 5, 1)
        assert result.state == "inactive"

    def test_the_sheet_shows_the_line(self, world):
        _flight(world, date(2026, 10, 1))
        client = login_as("view_operator")

        response = client.get(reverse("operator-detail", args=[world["operator"].pk]))

        body = response.content.decode()
        assert gettext("Last recorded flight") in body
        assert "01-10-2026" in body

    def test_the_sheet_says_when_there_are_no_flights(self, world):
        client = login_as("view_operator")

        response = client.get(reverse("operator-detail", args=[world["operator"].pk]))

        assert gettext("No flights in the digital logbook") in response.content.decode()
