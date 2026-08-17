"""OPS-7: log of GeoPlan.flight_permission changes."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

from .models import GeoPlan, GeoPlanPermissionLink


def _plan(cost_center, **kwargs):
    owner = User.objects.create_user(f"owner-{cost_center.pk}", password="pw")
    return GeoPlan.objects.create(
        title="Plan",
        cost_center=cost_center,
        created_by=owner,
        status="draft",
        **kwargs,
    )


def _permit(number, cost_center):
    return FlightPermission.objects.create(
        permission_number=number,
        cost_center=cost_center,
        purpose="Survey",
        valid_from=date(2026, 7, 1),
        valid_until=date(2026, 7, 10),
        location="Site",
    )


class TestSignal:
    @pytest.mark.django_db
    def test_creating_a_plan_with_no_permission_logs_nothing(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        _plan(cc)
        assert GeoPlanPermissionLink.objects.count() == 0

    @pytest.mark.django_db
    def test_linking_a_permission_logs_from_none_to_it(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        plan = _plan(cc)
        permit = _permit("P-1", cc)

        plan.flight_permission = permit
        plan.save(update_fields=["flight_permission", "updated_at"])

        link = GeoPlanPermissionLink.objects.get(plan=plan)
        assert link.previous_permission_id is None
        assert link.new_permission_id == permit.pk

    @pytest.mark.django_db
    def test_swapping_the_permission_logs_from_and_to(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        first, second = _permit("P-1", cc), _permit("P-2", cc)
        plan = _plan(cc, flight_permission=first)

        plan.flight_permission = second
        plan.save(update_fields=["flight_permission", "updated_at"])

        link = GeoPlanPermissionLink.objects.filter(plan=plan).latest("sequence")
        assert link.previous_permission_id == first.pk
        assert link.new_permission_id == second.pk

    @pytest.mark.django_db
    def test_unlinking_logs_to_none(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        permit = _permit("P-1", cc)
        plan = _plan(cc, flight_permission=permit)

        plan.flight_permission = None
        plan.save(update_fields=["flight_permission", "updated_at"])

        link = GeoPlanPermissionLink.objects.filter(plan=plan).latest("sequence")
        assert link.previous_permission_id == permit.pk
        assert link.new_permission_id is None

    @pytest.mark.django_db
    def test_resaving_without_changing_the_permission_logs_nothing(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        permit = _permit("P-1", cc)
        plan = _plan(cc, flight_permission=permit)

        plan.title = "Renamed"
        plan.save(update_fields=["title", "updated_at"])

        assert GeoPlanPermissionLink.objects.filter(plan=plan).count() == 0


class TestDetailPageShowsHistory:
    @pytest.mark.django_db
    def test_shows_the_link_history(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        permit = _permit("P-1", cc)
        plan = _plan(cc)
        plan.flight_permission = permit
        plan.save(update_fields=["flight_permission", "updated_at"])

        response = login_as("view_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )

        # R2.3: __str__ shows internal_folio now, not the DGAC folio ("P-1")
        # passed to _permit -- that is the point of the cascading fix.
        assert permit.internal_folio in response.content.decode()
        assert response.context["permission_links"].count() == 1
