"""LV-72 on the geo plan: the same traceability block as the flight permit.

A geo plan is a request that advances through review, so it earns the stepper.
The shared piece is `core.StatusFlowMixin`, extracted when this became the
second user -- the repo extracts on the second use, not in anticipation.
"""

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.test import Client
from django.urls import reverse

from apps.geo.models import GeoPlan, GeoPlanHistory
from apps.registry.models import CostCenter


def _client(*codenames, groups=()):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client, user


def _plan(status="draft"):
    owner = User.objects.create_user(f"owner-{status}", password="pw")
    return GeoPlan.objects.create(
        title="Plan Faena Norte",
        cost_center=CostCenter.objects.create(
            code=f"CC{CostCenter.objects.count() + 1}", name="Uno"
        ),
        created_by=owner,
        status=status,
    )


class TestTheStepper:
    @pytest.mark.django_db
    def test_a_draft_plan_is_on_its_first_step(self, db):
        steps = _plan().status_steps()

        assert [step["code"] for step in steps] == GeoPlan.STATUS_FLOW
        assert [step["state"] for step in steps] == [
            "current",
            "pending",
            "pending",
            "pending",
        ]

    @pytest.mark.django_db
    def test_an_approved_plan_has_everything_before_it_done(self, db):
        steps = _plan(status="approved").status_steps()

        assert [step["state"] for step in steps] == [
            "done",
            "done",
            "done",
            "current",
        ]

    @pytest.mark.django_db
    def test_a_rejected_plan_shows_where_it_stopped(self, db):
        """Rejected is where the flow stops, not a step on the way: a rejected
        plan goes back to editing, it does not carry on to approved."""
        steps = _plan(status="rejected").status_steps()

        assert [step["state"] for step in steps] == ["done", "blocked"]
        assert steps[-1]["code"] == GeoPlan.STATUS_REJECTED

    @pytest.mark.django_db
    def test_rejected_is_not_in_the_flow(self, db):
        assert GeoPlan.STATUS_REJECTED not in GeoPlan.STATUS_FLOW

    @pytest.mark.django_db
    def test_labels_come_from_the_choices(self, db):
        """The R1.1 trap: a literal list in a template drifting from the real
        choices."""
        labels = dict(GeoPlan.STATUS_CHOICES)

        for step in _plan(status="in_review").status_steps():
            assert step["label"] == labels[step["code"]]


class TestTheRenderedBlock:
    @pytest.mark.django_db
    def test_the_plan_page_carries_the_traceability_block(self, db):
        plan = _plan(status="in_review")
        client, user = _client("view_geoplan", groups=["Operations"])
        GeoPlanHistory.objects.create(
            plan=plan,
            previous_status="editing",
            new_status="in_review",
            changed_by=user.username,
            changed_by_user=user,
            notes="Enviado a revisión",
        )

        content = client.get(
            reverse("geo-plan-detail", args=[plan.pk])
        ).content.decode()

        assert "status-step is-current" in content
        assert "Operations" in content
        assert "Enviado a revisión" in content

    @pytest.mark.django_db
    def test_history_is_oldest_first(self, db):
        plan = _plan(status="approved")
        client, user = _client("view_geoplan")
        for previous, new in (("draft", "editing"), ("editing", "in_review")):
            GeoPlanHistory.objects.create(
                plan=plan,
                previous_status=previous,
                new_status=new,
                changed_by=user.username,
                changed_by_user=user,
            )

        response = client.get(reverse("geo-plan-detail", args=[plan.pk]))

        assert [entry.new_status for entry in response.context["history"]] == [
            "editing",
            "in_review",
        ]

    @pytest.mark.django_db
    def test_the_roles_do_not_cost_a_query_per_row(self, db):
        """Same guard as on the permit: unprefetched, the role is one query per
        entry -- the shape this project already paid for twice (V.18/V.19)."""
        client, user = _client("view_geoplan", groups=["Operations"])
        small = _entries_for(_plan(status="editing"), user, 2)
        large = _entries_for(_plan(status="approved"), user, 12)
        client.get(reverse("geo-plan-detail", args=[small.pk]))
        client.get(reverse("geo-plan-detail", args=[large.pk]))

        assert _query_count(client, small) == _query_count(client, large)


def _entries_for(plan, user, count):
    for index in range(count):
        GeoPlanHistory.objects.create(
            plan=plan,
            previous_status="draft",
            new_status="editing",
            changed_by=user.username,
            changed_by_user=user,
            notes=f"n{index}",
        )
    return plan


def _query_count(client, plan):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as captured:
        client.get(reverse("geo-plan-detail", args=[plan.pk]))
    return len(captured)
