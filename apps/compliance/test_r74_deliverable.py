"""R7.4: deliverable quality control (ISO 9001 8.5.1 / 8.6).

The clause asks for achieved-vs-required metrics, an internal validation before
release, and agreed acceptance criteria. The criteria live on the contract
(`CostCenter`), not on each deliverable: a threshold typed per row is an
opinion per record, not an agreed criterion.

The central design point these cover: **a contract with no thresholds has no
gate**, and its deliverables are recorded without a verdict. That is what makes
the feature usable before the negotiated numbers are known -- they are loaded
per contract, without a code change.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .models import Deliverable


def _contract(**thresholds):
    return CostCenter.objects.create(code="CC1", name="Uno", **thresholds)


def _deliverable(cost_center, **metrics):
    return Deliverable.objects.create(
        title="Levantamiento Mina Norte", cost_center=cost_center, **metrics
    )


class TestAcceptanceIsDerived:
    @pytest.mark.django_db
    def test_a_contract_without_thresholds_yields_no_verdict(self, db):
        """The whole reason this ships before the contract numbers are known:
        no criteria means nothing to judge, not a failure."""
        deliverable = _deliverable(_contract(), gsd_achieved_cm=Decimal("3.0"))

        assert deliverable.acceptance_checks() == []
        assert deliverable.meets_acceptance_criteria is None

    @pytest.mark.django_db
    def test_metrics_not_recorded_yet_yield_no_verdict(self, db):
        contract = _contract(required_gsd_cm=Decimal("5.0"))
        deliverable = _deliverable(contract)

        assert deliverable.meets_acceptance_criteria is None

    @pytest.mark.django_db
    def test_meeting_every_defined_threshold_passes(self, db):
        contract = _contract(
            required_gsd_cm=Decimal("5.0"),
            max_rmse_xy_cm=Decimal("10.0"),
            max_rmse_z_cm=Decimal("15.0"),
        )
        deliverable = _deliverable(
            contract,
            gsd_achieved_cm=Decimal("3.2"),
            rmse_xy_cm=Decimal("8.0"),
            rmse_z_cm=Decimal("12.0"),
        )

        assert len(deliverable.acceptance_checks()) == 3
        assert deliverable.meets_acceptance_criteria is True

    @pytest.mark.django_db
    def test_a_single_missed_threshold_fails_the_whole_deliverable(self, db):
        contract = _contract(
            required_gsd_cm=Decimal("5.0"), max_rmse_z_cm=Decimal("10.0")
        )
        deliverable = _deliverable(
            contract,
            gsd_achieved_cm=Decimal("3.0"),  # passes
            rmse_z_cm=Decimal("18.0"),  # fails
        )

        assert deliverable.meets_acceptance_criteria is False

    @pytest.mark.django_db
    def test_exactly_at_the_threshold_passes(self, db):
        """The agreed limit is what is allowed, not the first value refused."""
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("10.0"))

        assert deliverable.meets_acceptance_criteria is True

    @pytest.mark.django_db
    def test_only_criteria_with_both_sides_are_assessed(self, db):
        """A threshold with no measurement, or a measurement with no
        threshold, is left out rather than counted as a pass."""
        contract = _contract(
            required_gsd_cm=Decimal("5.0"), max_rmse_z_cm=Decimal("10.0")
        )
        deliverable = _deliverable(contract, gsd_achieved_cm=Decimal("3.0"))

        checks = deliverable.acceptance_checks()

        assert len(checks) == 1
        assert deliverable.meets_acceptance_criteria is True


class TestValidationFreezesTheThresholds:
    @pytest.mark.django_db
    def test_validating_signs_and_freezes(self, db):
        contract = _contract(required_gsd_cm=Decimal("5.0"))
        deliverable = _deliverable(contract, gsd_achieved_cm=Decimal("3.0"))
        user = User.objects.create_user("validator", password="pw")

        deliverable.validate_quality(user=user)

        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_VALIDATED
        assert deliverable.validated_by == user
        assert deliverable.validated_at is not None
        assert deliverable.applied_required_gsd_cm == Decimal("5.00")

    @pytest.mark.django_db
    def test_renegotiating_the_contract_does_not_rewrite_an_accepted_verdict(self, db):
        """Same criterion as purpose_legacy in R3.1: history stays true to the
        rules that were in force when it was judged."""
        contract = _contract(required_gsd_cm=Decimal("5.0"))
        deliverable = _deliverable(contract, gsd_achieved_cm=Decimal("4.0"))
        deliverable.validate_quality(user=None)

        # The contract is renegotiated to something stricter afterwards.
        contract.required_gsd_cm = Decimal("2.0")
        contract.save(update_fields=["required_gsd_cm"])
        deliverable.refresh_from_db()

        assert deliverable.meets_acceptance_criteria is True


class TestTheReleaseGate:
    @pytest.mark.django_db
    def test_an_unassessed_deliverable_releases_freely(self, db):
        """With no agreed criteria there is nothing to enforce; inventing a
        gate here would be a rule nobody agreed to."""
        deliverable = _deliverable(_contract())

        assert deliverable.can_release is True

    @pytest.mark.django_db
    def test_a_passing_deliverable_releases(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("6.0"))

        assert deliverable.can_release is True

    @pytest.mark.django_db
    def test_a_failing_deliverable_is_blocked_until_a_reason_is_written(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("20.0"))

        assert deliverable.can_release is False

        deliverable.release_waiver_reason = "Cliente acepta con nota tecnica 4/2026"
        assert deliverable.can_release is True

    @pytest.mark.django_db
    def test_whitespace_is_not_a_reason(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("20.0"))
        deliverable.release_waiver_reason = "   "

        assert deliverable.can_release is False


class TestTheViews:
    @pytest.mark.django_db
    def test_releasing_below_criteria_without_a_reason_is_refused(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("20.0"))
        deliverable.validate_quality(user=None)
        client = login_as("view_deliverable", "change_deliverable")

        response = client.post(reverse("deliverable-release", args=[deliverable.pk]))

        assert response.status_code == 302
        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_VALIDATED

    @pytest.mark.django_db
    def test_releasing_below_criteria_with_a_reason_is_recorded(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("20.0"))
        deliverable.validate_quality(user=None)
        client = login_as("view_deliverable", "change_deliverable")

        client.post(
            reverse("deliverable-release", args=[deliverable.pk]),
            {"waiver_reason": "Cliente acepta con nota tecnica 4/2026"},
        )

        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_RELEASED
        assert "nota tecnica" in deliverable.release_waiver_reason

    @pytest.mark.django_db
    def test_the_waiver_is_visible_afterwards(self, db):
        """A documented exception that nobody can see afterwards is not
        documented."""
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        deliverable = _deliverable(contract, rmse_xy_cm=Decimal("20.0"))
        deliverable.validate_quality(user=None)
        client = login_as("view_deliverable", "change_deliverable")
        client.post(
            reverse("deliverable-release", args=[deliverable.pk]),
            {"waiver_reason": "Cliente acepta con nota tecnica 4/2026"},
        )

        content = client.get(
            reverse("deliverable-detail", args=[deliverable.pk])
        ).content.decode()

        assert "nota tecnica 4/2026" in content

    @pytest.mark.django_db
    def test_release_requires_validation_first(self, db):
        """ISO 8.6 asks for internal validation *before* release, so draft
        cannot jump the queue."""
        deliverable = _deliverable(_contract())
        client = login_as("view_deliverable", "change_deliverable")

        client.post(reverse("deliverable-release", args=[deliverable.pk]))

        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_DRAFT

    @pytest.mark.django_db
    def test_a_released_deliverable_cannot_be_rejected(self, db):
        deliverable = _deliverable(_contract())
        deliverable.status = Deliverable.STATUS_RELEASED
        deliverable.save(update_fields=["status"])
        client = login_as("view_deliverable", "change_deliverable")

        client.post(reverse("deliverable-reject", args=[deliverable.pk]))

        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_RELEASED

    @pytest.mark.django_db
    def test_validating_requires_the_change_permission(self, db):
        deliverable = _deliverable(_contract())
        client = login_as("view_deliverable")

        response = client.post(reverse("deliverable-validate", args=[deliverable.pk]))

        assert response.status_code == 403
        deliverable.refresh_from_db()
        assert deliverable.status == Deliverable.STATUS_DRAFT

    @pytest.mark.django_db
    def test_the_list_requires_view_permission(self, db):
        response = login_as().get(reverse("deliverable-list"))

        assert response.status_code == 403

    @pytest.mark.django_db
    def test_the_list_shows_the_verdict(self, db):
        contract = _contract(max_rmse_xy_cm=Decimal("10.0"))
        _deliverable(contract, rmse_xy_cm=Decimal("20.0"))
        _deliverable(_contract2())

        content = (
            login_as("view_deliverable")
            .get(reverse("deliverable-list"))
            .content.decode()
        )

        assert "Bajo los criterios" in content
        assert "Sin evaluar" in content


def _contract2():
    return CostCenter.objects.create(code="CC2", name="Dos")
