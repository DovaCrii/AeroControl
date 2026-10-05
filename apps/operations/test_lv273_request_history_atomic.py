"""LV-273 (`T1.3`, segundo modelo): el historial de estados de una solicitud de vuelo se
escribe **con** el guardado, no antes de él.

Mismo defecto y mismo arreglo que `LV-270` (`FlightPermission`): la señal `pre_save`
corría antes del bloque atómico de `Model.save`, así que un guardado que fallaba
dejaba una fila de historial con un cambio que nunca ocurrió.

Orden seguido: estas pruebas se escribieron **antes** del cambio, contra la señal.
Las de comportamiento pasan con las dos implementaciones; las del defecto
(`TestAFailedSaveLeavesNoHistory`) fallan con la vieja.
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.operations.models import FlightRequest, FlightRequestHistory
from apps.registry.models import CostCenter

pytestmark = pytest.mark.django_db


def _request(title="Quebrada km 13", status=FlightRequest.STATUS_PREPARED):
    centre, _made = CostCenter.objects.get_or_create(
        code="CC273", defaults={"name": "Faena 273", "operates_flights": True}
    )
    return FlightRequest.objects.create(
        title=title,
        cost_center=centre,
        status=status,
        center_lat=Decimal("-23.650000"),
        center_lon=Decimal("-70.400000"),
    )


def _rows(request):
    return list(
        FlightRequestHistory.objects.filter(request=request).order_by("sequence")
    )


class TestWhatDoesNotChange:
    def test_a_status_change_writes_one_row_with_who_and_why(self):
        user = get_user_model().objects.create_user("ana", password="x")
        request = _request()
        request._changed_by = "Ana"
        request._changed_by_user = user
        request._transition_notes = "ingresada en SIGO"
        request.status = FlightRequest.STATUS_FILED

        request.save()

        [row] = _rows(request)
        assert (row.previous_status, row.new_status) == ("prepared", "filed")
        assert row.changed_by == "Ana"
        assert row.changed_by_user == user
        assert row.notes == "ingresada en SIGO"

    def test_without_an_attribution_the_actor_is_system(self):
        request = _request()
        request.status = FlightRequest.STATUS_FILED

        request.save()

        [row] = _rows(request)
        assert row.changed_by == "system"
        assert row.changed_by_user is None
        assert row.notes == ""

    def test_creating_a_request_writes_no_history(self):
        assert _rows(_request(status=FlightRequest.STATUS_FILED)) == []

    def test_saving_without_changing_the_status_writes_no_history(self):
        request = _request()
        request.title = "Otro titulo"

        request.save()

        assert _rows(request) == []

    def test_two_changes_are_two_rows_in_order(self):
        request = _request()
        request.status = FlightRequest.STATUS_FILED
        request.save()
        request.status = FlightRequest.STATUS_LINKED
        request.save()

        steps = [(row.previous_status, row.new_status) for row in _rows(request)]
        assert steps == [("prepared", "filed"), ("filed", "linked")]

    def test_a_row_loaded_fresh_is_compared_against_the_database(self):
        """El caso de la vista: se lee de la base, se cambia, se guarda."""
        _request(title="Fresca")
        request = FlightRequest.objects.get(title="Fresca")
        request.status = FlightRequest.STATUS_FILED

        request.save(update_fields=["status", "updated_at"])

        assert len(_rows(request)) == 1


class TestTheStatusIsOnlyRecordedWhenItIsSaved:
    def test_update_fields_that_leave_the_status_out_write_no_history(self):
        """La base **no** cambia de estado en ese guardado, así que el historial no
        puede decir que sí. La señal vieja lo escribía igual."""
        request = _request()
        request.status = FlightRequest.STATUS_FILED

        request.save(update_fields=["title"])

        assert _rows(request) == []
        assert (
            FlightRequest.objects.get(pk=request.pk).status
            == FlightRequest.STATUS_PREPARED
        )


@pytest.mark.django_db(transaction=True)
class TestAFailedSaveLeavesNoHistory:
    def test_a_foreign_key_violation_does_not_leave_an_orphan_row(self):
        """El defecto: el cambio de estado no llega a la base, pero el historial
        decía que sí."""
        request = _request(status=FlightRequest.STATUS_PREPARED)
        request.cost_center_id = uuid.uuid4()  # una faena que no existe
        request.status = FlightRequest.STATUS_FILED

        with pytest.raises(IntegrityError):
            request.save()

        assert _rows(request) == []
        assert (
            FlightRequest.objects.get(pk=request.pk).status
            == FlightRequest.STATUS_PREPARED
        )
