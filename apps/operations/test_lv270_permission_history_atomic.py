"""LV-270 (`T1.3`, paso 1 y 2 para `FlightPermission`): el historial de estados se
escribe **con** el guardado, no antes de él.

Hasta aquí lo escribía una señal `pre_save`, que corre **antes** del bloque atómico
de `Model.save`. Comprobado el 2026-10-05: con una violación de unicidad, un permiso
que pasaba de `approved` a `denied` dejó `PermissionHistory` con `approved → denied`
mientras la base conservaba `approved` — un registro de trazabilidad que afirma un
cambio que nunca ocurrió.

Estas pruebas fijan **primero** el comportamiento que no debe cambiar (la fila, el
actor, el usuario, las notas, nada al crear ni sin cambio) y después el defecto
(`TestAFailedSaveLeavesNoHistory`). Se escribieron antes del cambio, contra la
señal: las de comportamiento pasan con las dos implementaciones, y la del defecto
falla con la vieja.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.operations.models import FlightPermission, PermissionHistory
from apps.registry.models import CostCenter

pytestmark = pytest.mark.django_db


def _permit(number, status=FlightPermission.STATUS_REQUESTED):
    centre, _made = CostCenter.objects.get_or_create(
        code="CC270", defaults={"name": "Faena 270", "operates_flights": True}
    )
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        location="Sector",
        area_type="unpopulated",
        permission_number=number,
        status=status,
    )


def _rows(permit):
    return list(
        PermissionHistory.objects.filter(permission=permit).order_by("sequence")
    )


class TestWhatDoesNotChange:
    def test_a_status_change_writes_one_row_with_who_and_why(self):
        user = get_user_model().objects.create_user("ana", password="x")
        permit = _permit("P-1")
        permit._changed_by = "Ana"
        permit._changed_by_user = user
        permit._transition_notes = "con la carta del mandante"
        permit.status = FlightPermission.STATUS_APPROVED

        permit.save()

        [row] = _rows(permit)
        assert (row.previous_status, row.new_status) == (
            FlightPermission.STATUS_REQUESTED,
            FlightPermission.STATUS_APPROVED,
        )
        assert row.changed_by == "Ana"
        assert row.changed_by_user == user
        assert row.notes == "con la carta del mandante"

    def test_without_an_attribution_the_actor_is_system(self):
        permit = _permit("P-2")
        permit.status = FlightPermission.STATUS_DENIED

        permit.save()

        [row] = _rows(permit)
        assert row.changed_by == "system"
        assert row.changed_by_user is None
        assert row.notes == ""

    def test_creating_a_permit_writes_no_history(self):
        assert _rows(_permit("P-3", status=FlightPermission.STATUS_APPROVED)) == []

    def test_saving_without_changing_the_status_writes_no_history(self):
        permit = _permit("P-4")
        permit.location = "Otro sector"

        permit.save()

        assert _rows(permit) == []

    def test_two_changes_are_two_rows_in_order(self):
        permit = _permit("P-5")
        permit.status = FlightPermission.STATUS_APPROVED
        permit.save()
        permit.status = FlightPermission.STATUS_DENIED
        permit.save()

        steps = [(row.previous_status, row.new_status) for row in _rows(permit)]
        assert steps == [("requested", "approved"), ("approved", "denied")]

    def test_a_row_loaded_fresh_is_compared_against_the_database(self):
        """El caso de la vista: se lee de la base, se cambia, se guarda."""
        _permit("P-6")
        permit = FlightPermission.objects.get(permission_number="P-6")
        permit.status = FlightPermission.STATUS_APPROVED

        permit.save()

        assert len(_rows(permit)) == 1


class TestTheStatusIsOnlyRecordedWhenItIsSaved:
    def test_update_fields_that_leave_the_status_out_write_no_history(self):
        """`update_fields` sin `status`: la base **no** cambia de estado, así que
        el historial no puede decir que sí. La señal vieja lo escribía igual."""
        permit = _permit("P-7")
        permit.status = FlightPermission.STATUS_APPROVED

        permit.save(update_fields=["location"])

        assert _rows(permit) == []
        assert (
            FlightPermission.objects.get(pk=permit.pk).status
            == FlightPermission.STATUS_REQUESTED
        )

    def test_update_fields_that_include_the_status_write_it(self):
        permit = _permit("P-8")
        permit.status = FlightPermission.STATUS_APPROVED

        permit.save(update_fields=["status", "updated_at"])

        assert len(_rows(permit)) == 1


@pytest.mark.django_db(transaction=True)
class TestAFailedSaveLeavesNoHistory:
    def test_a_unique_violation_does_not_leave_an_orphan_row(self):
        """El defecto medido: antes, esta prueba veía `approved → denied` en el
        historial con `approved` en la base."""
        first = _permit("P-9")
        second = _permit("P-10", status=FlightPermission.STATUS_APPROVED)
        second.permission_number = first.permission_number  # viola la unicidad
        second.status = FlightPermission.STATUS_DENIED

        with pytest.raises(IntegrityError):
            second.save()

        assert _rows(second) == []
        assert (
            FlightPermission.objects.get(pk=second.pk).status
            == FlightPermission.STATUS_APPROVED
        )
