"""LV-89: "can we operate today?" on the panel, instead of two thin pie charts.

What is worth pinning is not the arithmetic but the definitions, because each
one was a decision: what counts as available, what counts as insured, and which
aircraft belong in the denominator at all.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.views import panel_readiness
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


def _aircraft(registration, **kwargs):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


def _by_label(result, index):
    return result["readiness"][index]


@pytest.mark.django_db
class TestFleetAvailable:
    def test_a_retired_aircraft_is_not_unavailable_it_left_the_fleet(self):
        """Same reasoning as `kpis.fleet_availability`: counting it would make
        the figure sag permanently for a good decision."""
        _aircraft("CC-OK", status="active")
        _aircraft("CC-RET", status="retired")

        fleet = _by_label(panel_readiness(TODAY), 0)

        assert (fleet["count"], fleet["total"]) == (1, 1)
        assert fleet["pct"] == 100.0

    def test_damaged_and_in_maintenance_count_against_it(self):
        _aircraft("CC-OK", status="active")
        _aircraft("CC-DMG", status="damaged")
        _aircraft("CC-MNT", status="maintenance")

        fleet = _by_label(panel_readiness(TODAY), 0)

        assert (fleet["count"], fleet["total"]) == (1, 3)
        assert fleet["shortfall"] == 2

    def test_it_carries_the_agreed_target(self):
        from apps.compliance.kpis import FLEET_AVAILABILITY_TARGET

        _aircraft("CC-OK", status="active")

        assert _by_label(panel_readiness(TODAY), 0)["target"] == (
            FLEET_AVAILABILITY_TARGET
        )

    def test_an_empty_fleet_has_no_percentage_rather_than_a_zero(self):
        """0% would read as "everything is grounded" when the truth is "there is
        nothing to report"."""
        assert _by_label(panel_readiness(TODAY), 0)["pct"] is None


@pytest.mark.django_db
class TestInsuranceUpToDate:
    def test_a_lapsed_policy_does_not_count_however_the_status_reads(self):
        """ "Up to date" means on file *and* still valid. An aircraft whose
        insurance lapsed yesterday is not covered, whatever the status says."""
        _aircraft(
            "CC-LAPSED",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY - timedelta(days=1),
        )
        _aircraft(
            "CC-OK",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=200),
        )

        insurance = _by_label(panel_readiness(TODAY), 1)

        assert (insurance["count"], insurance["total"]) == (1, 2)
        assert insurance["shortfall"] == 1

    def test_a_filing_in_progress_is_not_yet_cover(self):
        _aircraft(
            "CC-FILED",
            insurance_status=Aircraft.INSURANCE_STATUS_FILED,
            insurance_expiry=TODAY + timedelta(days=100),
        )

        assert _by_label(panel_readiness(TODAY), 1)["count"] == 0

    def test_what_expires_within_30_days_is_counted_separately(self):
        _aircraft(
            "CC-SOON",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=10),
        )
        _aircraft(
            "CC-LATER",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=200),
        )

        insurance = _by_label(panel_readiness(TODAY), 1)

        assert insurance["count"] == 2
        assert insurance["soon"] == 1


@pytest.mark.django_db
class TestCredentials:
    def test_an_operator_with_no_credential_date_counts_as_missing(self):
        """A null is exactly the gap LV-74 is about: it raises no alert, so the
        panel has to say it out loud."""
        Operator.objects.create(employee_id="E1", full_name="Sin fecha")
        Operator.objects.create(
            employee_id="E2",
            full_name="Al día",
            credential_expiry=TODAY + timedelta(days=100),
        )

        credentials = _by_label(panel_readiness(TODAY), 2)

        assert (credentials["count"], credentials["total"]) == (1, 2)
        assert credentials["shortfall"] == 1


@pytest.mark.django_db
class TestTheCostCenterFilter:
    def test_the_strip_follows_the_panel_filter(self):
        north = CostCenter.objects.create(code="CC-N")
        south = CostCenter.objects.create(code="CC-S")
        _aircraft("CC-1", status="active", cost_center=north)
        _aircraft("CC-2", status="damaged", cost_center=south)

        fleet = _by_label(panel_readiness(TODAY, north), 0)

        assert (fleet["count"], fleet["total"]) == (1, 1)


@pytest.mark.django_db
class TestOnThePage:
    def test_the_panel_renders_the_strip_and_not_the_retired_charts(self):
        _aircraft("CC-OK", status="active")
        User.objects.create_user("panel", password="pw")
        client = Client()
        assert client.login(username="panel", password="pw")

        response = client.get(reverse("dashboard"))
        content = response.content.decode()

        assert response.status_code == 200
        assert len(response.context["readiness"]) == 3
        assert "readiness-strip" in content
        # The two charts LV-89 replaced, and the header button that promised the
        # registry and opened cost centers.
        assert "chart-aircraft-status" not in content
        assert "statusChart" not in content
        assert "Abrir registro" not in content
