"""LV-72: the permit's traceability screen, shaped like SIGO's.

SIGO (the DGAC's own system) shows a request as a horizontal stepper plus a
numbered "Historial de Solicitud" with Action · User · Role · Date. Operators
read that screen every day, so copying the shape removes a mental translation
-- and it is the order an auditor reads evidence in.

Nothing new is stored: `PermissionHistory` already had the actor, the
transition and the notes. These cover the presentation and, above all, that the
steps are **derived from the model** rather than written out in the template
(the R1.1 defect).
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightPermission, PermissionHistory
from apps.registry.models import CostCenter


def _permit(status="requested", code=None):
    # The code is unique per tenant, so a test creating two permits has to vary
    # it rather than reuse "CC1".
    code = code or f"CC{CostCenter.objects.count() + 1}"
    return FlightPermission.objects.create(
        cost_center=CostCenter.objects.create(code=code, name="Uno"),
        purpose="photogrammetry",
        valid_from=date(2026, 8, 1),
        valid_until=date(2026, 8, 10),
        location="Faena Norte",
        area_type="unpopulated",
        status=status,
    )


class TestTheStepperComesFromTheModel:
    @pytest.mark.django_db
    def test_a_new_permit_is_on_its_first_step(self, db):
        steps = _permit().status_steps()

        assert [step["code"] for step in steps] == FlightPermission.STATUS_FLOW
        assert [step["state"] for step in steps] == ["current", "pending", "pending"]

    @pytest.mark.django_db
    def test_an_approved_permit_has_its_first_step_done(self, db):
        steps = _permit(status="approved").status_steps()

        assert [step["state"] for step in steps] == ["done", "current", "pending"]

    @pytest.mark.django_db
    def test_a_completed_permit_is_on_the_last_step(self, db):
        steps = _permit(status="completed").status_steps()

        assert [step["state"] for step in steps] == ["done", "done", "current"]

    @pytest.mark.django_db
    def test_a_denied_permit_shows_where_it_stopped(self, db):
        """Not the full flow greyed out: that would imply the remaining steps
        are still ahead of it. A denied permit is not going anywhere."""
        steps = _permit(status="denied").status_steps()

        assert [step["code"] for step in steps] == ["requested", "denied"]
        assert [step["state"] for step in steps] == ["done", "blocked"]

    @pytest.mark.django_db
    def test_denied_is_not_part_of_the_flow(self, db):
        """It is where the flow stops, not a step on the way anywhere."""
        assert FlightPermission.STATUS_DENIED not in FlightPermission.STATUS_FLOW

    @pytest.mark.django_db
    def test_labels_come_from_the_choices_not_from_literals(self, db):
        """R1.1 was a hand-written list in a template drifting from the real
        choices. Every step's label must be the one STATUS_CHOICES declares."""
        labels = dict(FlightPermission.STATUS_CHOICES)

        for step in _permit(status="approved").status_steps():
            assert step["label"] == labels[step["code"]]


class TestTheHistoryTable:
    @pytest.mark.django_db
    def test_shows_who_with_which_role_and_when(self, db):
        """A trace that says who but not in what capacity answers half the
        auditor's question."""
        permit = _permit(status="approved")
        client = login_as("view_flightpermission", groups=["Compliance"])
        user = client.user
        PermissionHistory.objects.create(
            permission=permit,
            previous_status="requested",
            new_status="approved",
            changed_by=user.username,
            changed_by_user=user,
            notes="Autorizada por la DGAC",
        )

        content = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "Compliance" in content
        assert user.username in content
        assert "Autorizada por la DGAC" in content

    @pytest.mark.django_db
    def test_entries_are_numbered_oldest_first(self, db):
        """SIGO numbers the trace 1..N in the order things happened, and "in
        what order" is half of what the screen is for -- so this overrides the
        model's newest-first default."""
        permit = _permit(status="completed")
        client = login_as("view_flightpermission")
        user = client.user
        for previous, new in (("requested", "approved"), ("approved", "completed")):
            PermissionHistory.objects.create(
                permission=permit,
                previous_status=previous,
                new_status=new,
                changed_by=user.username,
                changed_by_user=user,
            )

        response = client.get(reverse("permission-detail", args=[permit.pk]))
        history = list(response.context["history"])

        assert [entry.new_status for entry in history] == ["approved", "completed"]

    @pytest.mark.django_db
    def test_a_user_with_no_group_does_not_break_the_row(self, db):
        permit = _permit(status="approved")
        client = login_as("view_flightpermission")
        user = client.user
        PermissionHistory.objects.create(
            permission=permit,
            previous_status="requested",
            new_status="approved",
            changed_by=user.username,
            changed_by_user=user,
        )

        response = client.get(reverse("permission-detail", args=[permit.pk]))

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_the_roles_do_not_cost_a_query_per_row(self, db):
        """`{{ h.changed_by_user.groups.all }}` unprefetched is one query per
        entry -- the shape that already cost this project twice (V.18/V.19).

        Compares two permits, one with 2 history entries and one with 12: the
        page's query count must be the same. Pinning an absolute number instead
        would break on any unrelated change and say nothing about scaling.
        """
        client = login_as("view_flightpermission", groups=["Operations"])
        user = client.user
        small = _entries_for(_permit(status="approved"), user, 2)
        large = _entries_for(_permit(status="approved"), user, 12)

        # Warm whatever is cached per process (content types, permissions) so
        # the first page does not pay for both.
        client.get(reverse("permission-detail", args=[small.pk]))
        client.get(reverse("permission-detail", args=[large.pk]))

        assert _query_count(client, small) == _query_count(client, large)


def _entries_for(permit, user, count):
    for index in range(count):
        PermissionHistory.objects.create(
            permission=permit,
            previous_status="requested",
            new_status="approved",
            changed_by=user.username,
            changed_by_user=user,
            notes=f"n{index}",
        )
    return permit


def _query_count(client, permit):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as captured:
        client.get(reverse("permission-detail", args=[permit.pk]))
    return len(captured)


class TestTheRenderedPage:
    @pytest.mark.django_db
    def test_the_stepper_renders_every_step_of_the_flow(self, db):
        permit = _permit(status="approved")
        client = login_as("view_flightpermission")
        _user = client.user

        content = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert content.count("status-step is-") == len(FlightPermission.STATUS_FLOW)
        assert "status-step is-done" in content
        assert "status-step is-current" in content

    @pytest.mark.django_db
    def test_a_denied_permit_renders_the_blocked_step(self, db):
        permit = _permit(status="denied")
        client = login_as("view_flightpermission")
        _user = client.user

        content = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "status-step is-blocked" in content
