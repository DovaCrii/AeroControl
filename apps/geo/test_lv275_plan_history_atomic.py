"""LV-275 (`T1.3`, cuarto modelo): el historial de estados de un plan geoespacial se
escribe **con** el guardado, y también el registro de con qué permiso se enlazó.

`GeoPlan` tiene **dos** señales `pre_save`: el historial de estados y
`track_flight_permission_link` (`OPS-7`), que escribe `GeoPlanPermissionLink` cuando
cambia `flight_permission`. Las dos escribían **antes** del bloque atómico de
`Model.save`, así que un guardado que fallaba dejaba las dos filas con un cambio que
no ocurrió. Las señales `pre_save` corren dentro de `Model.save`: al envolver el
guardado en la transacción del mixin, la segunda entra en ella sin moverla.

Orden seguido: estas pruebas se escribieron **antes** del cambio, contra las dos
señales. Las de comportamiento pasan con las dos implementaciones; las del defecto
(`TestAFailedSaveLeavesNothingBehind`) fallan con la vieja.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.geo.models import GeoPlan, GeoPlanHistory, GeoPlanPermissionLink
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

pytestmark = pytest.mark.django_db


def _centre():
    centre, _made = CostCenter.objects.get_or_create(
        code="CC275", defaults={"name": "Faena 275", "operates_flights": True}
    )
    return centre


def _plan(title="Plan 275", status=GeoPlan.STATUS_DRAFT):
    user, _made = get_user_model().objects.get_or_create(username="planner")
    return GeoPlan.objects.create(
        title=title, cost_center=_centre(), created_by=user, status=status
    )


def _permit(number):
    return FlightPermission.objects.create(
        cost_center=_centre(),
        purpose="photogrammetry",
        location="Sector",
        area_type="unpopulated",
        permission_number=number,
    )


def _rows(plan):
    return list(GeoPlanHistory.objects.filter(plan=plan).order_by("sequence"))


def _links(plan):
    return list(GeoPlanPermissionLink.objects.filter(plan=plan).order_by("sequence"))


class TestTheHistoryWhatDoesNotChange:
    def test_a_status_change_writes_one_row_with_who(self):
        user = get_user_model().objects.create_user("ana", password="x")
        plan = _plan()
        plan._changed_by = "Ana"
        plan._changed_by_user = user
        plan.status = GeoPlan.STATUS_EDITING

        plan.save()

        [row] = _rows(plan)
        assert (row.previous_status, row.new_status) == ("draft", "editing")
        assert row.changed_by == "Ana"
        assert row.changed_by_user == user

    def test_without_an_attribution_the_actor_is_system(self):
        plan = _plan()
        plan.status = GeoPlan.STATUS_EDITING

        plan.save()

        [row] = _rows(plan)
        assert row.changed_by == "system"
        assert row.changed_by_user is None

    def test_creating_a_plan_writes_no_history(self):
        assert _rows(_plan(status=GeoPlan.STATUS_EDITING)) == []

    def test_saving_without_changing_the_status_writes_no_history(self):
        plan = _plan()
        plan.title = "Otro titulo"

        plan.save()

        assert _rows(plan) == []

    def test_two_changes_are_two_rows_in_order(self):
        plan = _plan()
        plan.status = GeoPlan.STATUS_EDITING
        plan.save()
        plan.status = GeoPlan.STATUS_IN_REVIEW
        plan.save()

        steps = [(row.previous_status, row.new_status) for row in _rows(plan)]
        assert steps == [("draft", "editing"), ("editing", "in_review")]

    def test_a_row_loaded_fresh_is_compared_against_the_database(self):
        _plan(title="Fresco")
        plan = GeoPlan.objects.get(title="Fresco")
        plan.status = GeoPlan.STATUS_EDITING

        plan.save(update_fields=["status", "updated_at"])

        assert len(_rows(plan)) == 1


class TestTheHistoryIsOnlyRecordedWhenTheStatusIsSaved:
    def test_update_fields_that_leave_the_status_out_write_no_history(self):
        plan = _plan()
        plan.status = GeoPlan.STATUS_EDITING

        plan.save(update_fields=["title"])

        assert _rows(plan) == []
        assert GeoPlan.objects.get(pk=plan.pk).status == GeoPlan.STATUS_DRAFT


class TestTheLinkToThePermitIsStillLogged:
    """`OPS-7`: la otra señal, que no se toca."""

    def test_linking_a_permit_writes_one_row(self):
        user = get_user_model().objects.create_user("bea", password="x")
        plan = _plan()
        permit = _permit("P-1")
        plan._changed_by_user = user
        plan.flight_permission = permit

        plan.save()

        [link] = _links(plan)
        assert link.previous_permission_id is None
        assert link.new_permission_id == permit.pk
        assert link.changed_by_user == user

    def test_changing_the_permit_remembers_the_previous_one(self):
        plan = _plan()
        first, second = _permit("P-1"), _permit("P-2")
        plan.flight_permission = first
        plan.save()
        plan.flight_permission = second
        plan.save()

        links = _links(plan)
        assert [link.new_permission_id for link in links] == [first.pk, second.pk]
        assert links[1].previous_permission_id == first.pk

    def test_saving_with_the_same_permit_writes_nothing(self):
        plan = _plan()
        plan.flight_permission = _permit("P-1")
        plan.save()
        plan.title = "Otro"
        plan.save()

        assert len(_links(plan)) == 1


@pytest.mark.django_db(transaction=True)
class TestAFailedSaveLeavesNothingBehind:
    def test_no_orphan_history_row(self):
        plan = _plan()
        plan.status = GeoPlan.STATUS_EDITING
        plan.title = None  # viola NOT NULL: el guardado falla

        with pytest.raises(IntegrityError):
            plan.save()

        assert _rows(plan) == []
        assert GeoPlan.objects.get(pk=plan.pk).status == GeoPlan.STATUS_DRAFT

    def test_no_orphan_permit_link(self):
        """Antes quedaba escrito «se enlazó el permiso X» sin que el plan lo tuviera."""
        plan = _plan()
        plan.flight_permission = _permit("P-1")
        plan.title = None  # el guardado falla

        with pytest.raises(IntegrityError):
            plan.save()

        assert _links(plan) == []
        assert GeoPlan.objects.get(pk=plan.pk).flight_permission_id is None
