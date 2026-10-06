"""LV-276 (`T1.3`, quinto y último modelo): el historial del trámite del seguro de una
aeronave se escribe **con** el guardado, y también el registro de sus movimientos.

`Aircraft` tiene **dos** señales `pre_save`: la del seguro (`track_status_changes`,
`LV-81`), que sigue el campo `insurance_status` —que **no** se llama `status`— y la de
ubicación (`track_aircraft_location`, `OPS-3`), que escribe un `ResourceMovementLog`.
Las dos escribían **antes** del bloque atómico de `Model.save`, así que un guardado que
fallaba dejaba las dos filas. Las señales `pre_save` corren dentro de `Model.save`: al
envolver el guardado en la transacción del mixin, la de ubicación entra en ella sin
moverla.

Con este modelo `core.signals.track_status_changes` ya no tiene a quién servir y se
retira.

Orden seguido: estas pruebas se escribieron **antes** del cambio, contra las dos
señales. Las de comportamiento pasan con las dos implementaciones; las del defecto
(`TestAFailedSaveLeavesNothingBehind`) fallan con la vieja.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.registry.models import Aircraft, InsuranceHistory, ResourceMovementLog

pytestmark = pytest.mark.django_db


def _aircraft(**extra):
    extra.setdefault("insurance_status", Aircraft.INSURANCE_STATUS_MISSING)
    return Aircraft.objects.create(
        registration="CC-276",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        **extra,
    )


def _rows(aircraft):
    return list(InsuranceHistory.objects.filter(aircraft=aircraft).order_by("sequence"))


def _moves(aircraft):
    return list(
        ResourceMovementLog.objects.filter(
            resource_kind="aircraft",
            resource_id=aircraft.pk,
            movement="location_changed",
        )
    )


class TestTheHistoryWhatDoesNotChange:
    def test_a_status_change_writes_one_row_with_who_and_why(self):
        user = get_user_model().objects.create_user("ana", password="x")
        aircraft = _aircraft()
        aircraft._changed_by = "Ana"
        aircraft._changed_by_user = user
        aircraft._transition_notes = "ingresada en la JAC"
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED

        aircraft.save()

        [row] = _rows(aircraft)
        assert (row.previous_status, row.new_status) == ("missing", "filed")
        assert row.changed_by == "Ana"
        assert row.changed_by_user == user
        assert row.notes == "ingresada en la JAC"

    def test_without_an_attribution_the_actor_is_system(self):
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED

        aircraft.save()

        [row] = _rows(aircraft)
        assert row.changed_by == "system"
        assert row.changed_by_user is None

    def test_creating_an_aircraft_writes_no_history(self):
        assert _rows(_aircraft(insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE)) == []

    def test_saving_without_changing_the_insurance_writes_no_history(self):
        aircraft = _aircraft()
        aircraft.model = "B"

        aircraft.save()

        assert _rows(aircraft) == []

    def test_the_aircraft_own_status_is_a_different_axis(self):
        """`Aircraft.status` (activa / dañada / mantención) **no** tiene historial: lo
        que se sigue es el trámite del seguro."""
        aircraft = _aircraft()
        aircraft.status = "damaged"

        aircraft.save()

        assert _rows(aircraft) == []

    def test_two_changes_are_two_rows_in_order(self):
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED
        aircraft.save()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_ACTIVE
        aircraft.save()

        steps = [(row.previous_status, row.new_status) for row in _rows(aircraft)]
        assert steps == [("missing", "filed"), ("filed", "active")]

    def test_the_jac_resolution_path_saves_with_update_fields_and_still_records(self):
        """Así guarda `sync_insurance_from_document` (`LV-159`): con `update_fields`
        que sí incluye `insurance_status`."""
        _aircraft()
        aircraft = Aircraft.objects.get(registration="CC-276")
        aircraft._changed_by_user = get_user_model().objects.create_user(
            "u", password="x"
        )
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_ACTIVE

        aircraft.save(update_fields=["updated_at", "insurance_status"])

        [row] = _rows(aircraft)
        assert (row.previous_status, row.new_status) == ("missing", "active")

    def test_the_maintenance_path_does_not_touch_the_insurance_history(self):
        """La señal de mantención guarda la aeronave con otros campos
        (`update_fields` sin `insurance_status`): no hay trámite que registrar."""
        aircraft = _aircraft()
        aircraft.current_location = "maintenance"
        aircraft.status = "maintenance"

        aircraft.save(
            update_fields=["current_location", "current_site", "status", "updated_at"]
        )

        assert _rows(aircraft) == []


class TestTheHistoryIsOnlyRecordedWhenTheInsuranceIsSaved:
    def test_update_fields_that_leave_it_out_write_no_history(self):
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED

        aircraft.save(update_fields=["model"])

        assert _rows(aircraft) == []
        assert (
            Aircraft.objects.get(pk=aircraft.pk).insurance_status
            == Aircraft.INSURANCE_STATUS_MISSING
        )


class TestTheLocationLogIsStillWritten:
    """`OPS-3`: la otra señal, que no se toca."""

    def test_moving_the_aircraft_writes_one_log_row(self):
        aircraft = _aircraft()
        aircraft.current_location = "maintenance"

        aircraft.save()

        assert len(_moves(aircraft)) == 1

    def test_saving_in_the_same_place_writes_nothing(self):
        aircraft = _aircraft()
        aircraft.model = "B"

        aircraft.save()

        assert _moves(aircraft) == []


@pytest.mark.django_db(transaction=True)
class TestAFailedSaveLeavesNothingBehind:
    def test_no_orphan_history_row(self):
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED
        aircraft.model = None  # viola NOT NULL: el guardado falla

        with pytest.raises(IntegrityError):
            aircraft.save()

        assert _rows(aircraft) == []
        assert (
            Aircraft.objects.get(pk=aircraft.pk).insurance_status
            == Aircraft.INSURANCE_STATUS_MISSING
        )

    def test_no_orphan_movement_row(self):
        """Antes quedaba escrito «se movió a mantención» sin que la aeronave se
        hubiera movido."""
        aircraft = _aircraft()
        aircraft.current_location = "maintenance"
        aircraft.model = None  # el guardado falla

        with pytest.raises(IntegrityError):
            aircraft.save()

        assert _moves(aircraft) == []
        assert Aircraft.objects.get(pk=aircraft.pk).current_location == "headquarters"
