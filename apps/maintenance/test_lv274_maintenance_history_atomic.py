"""LV-274 (`T1.3`, tercer modelo): el historial de estados de una mantención se escribe
**con** el guardado, no antes de él — y, de regalo, también lo que la mantención le
hace a la aeronave.

Mismo defecto y mismo arreglo que `LV-270` y `LV-273`. Aquí hay una segunda señal
`pre_save` (`sync_maintenance_status_transition`) que, al enviar una aeronave al
taller o al traerla de vuelta, **modifica la aeronave** antes de que la mantención se
guarde. Como las señales de `pre_save` corren dentro de `Model.save`, al envolver el
guardado en una transacción esa escritura entra en ella: si el guardado falla, la
aeronave tampoco queda en «mantención». No hace falta mover la señal para eso, y por
eso este paso **no la mueve** — ver `T1.3`.

Orden seguido: estas pruebas se escribieron **antes** del cambio, contra las dos
señales. Las de comportamiento pasan con las dos implementaciones; las del defecto
(`TestAFailedSaveLeavesNothingBehind`) fallan con la vieja.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.maintenance.models import MaintenanceHistory, MaintenanceRecord
from apps.registry.models import Aircraft

pytestmark = pytest.mark.django_db


def _aircraft(**extra):
    return Aircraft.objects.create(
        registration="CC-274",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        **extra,
    )


def _record(aircraft=None, status="pending"):
    return MaintenanceRecord.objects.create(
        aircraft=aircraft or _aircraft(),
        maintenance_type="scheduled",
        description="Inspeccion de 100 h",
        status=status,
    )


def _rows(record):
    return list(MaintenanceHistory.objects.filter(record=record).order_by("sequence"))


class TestTheHistoryWhatDoesNotChange:
    def test_a_status_change_writes_one_row_with_who_and_why(self):
        user = get_user_model().objects.create_user("ana", password="x")
        record = _record()
        record._changed_by = "Ana"
        record._changed_by_user = user
        record._transition_notes = "repuesto recibido"
        record.status = "in_progress"

        record.save()

        [row] = _rows(record)
        assert (row.previous_status, row.new_status) == ("pending", "in_progress")
        assert row.changed_by == "Ana"
        assert row.changed_by_user == user
        assert row.notes == "repuesto recibido"

    def test_without_an_attribution_the_actor_is_system(self):
        record = _record()
        record.status = "in_progress"

        record.save()

        [row] = _rows(record)
        assert row.changed_by == "system"
        assert row.changed_by_user is None

    def test_creating_a_record_writes_no_history(self):
        assert _rows(_record(status="in_progress")) == []

    def test_saving_without_changing_the_status_writes_no_history(self):
        record = _record()
        record.description = "Otra descripcion"

        record.save()

        assert _rows(record) == []

    def test_two_changes_are_two_rows_in_order(self):
        record = _record()
        record.status = "in_progress"
        record.save()
        record.status = "completed"
        record.save()

        steps = [(row.previous_status, row.new_status) for row in _rows(record)]
        assert steps == [("pending", "in_progress"), ("in_progress", "completed")]

    def test_the_completion_view_saves_with_update_fields_and_still_records(self):
        """Así guarda `MaintenanceTransition`: con `update_fields` que sí incluye
        `status`. Es el camino real de producción."""
        _record(status="in_progress")
        record = MaintenanceRecord.objects.get(description="Inspeccion de 100 h")
        record._changed_by = "demo"
        record.status = "completed"

        record.save(update_fields=["status", "updated_at"])

        [row] = _rows(record)
        assert (row.previous_status, row.new_status) == ("in_progress", "completed")
        assert row.changed_by == "demo"


class TestTheHistoryIsOnlyRecordedWhenTheStatusIsSaved:
    def test_update_fields_that_leave_the_status_out_write_no_history(self):
        record = _record()
        record.status = "in_progress"

        record.save(update_fields=["description"])

        assert _rows(record) == []
        assert MaintenanceRecord.objects.get(pk=record.pk).status == "pending"


class TestWhatTheMaintenanceDoesToTheAircraft:
    """Lo que la señal de mantención ya hacía y **no puede cambiar**."""

    def test_sending_it_to_the_workshop_takes_the_aircraft_out_of_service(self):
        aircraft = _aircraft()
        record = _record(aircraft)
        record.status = "sent"

        record.save()

        aircraft.refresh_from_db()
        assert aircraft.current_location == "maintenance"
        assert aircraft.status == "maintenance"

    def test_completing_from_in_transit_brings_the_aircraft_home(self):
        aircraft = _aircraft(current_location="maintenance", status="maintenance")
        record = _record(aircraft, status="in_transit")
        record.status = "completed"

        record.save()

        aircraft.refresh_from_db()
        assert aircraft.current_location == "headquarters"
        assert aircraft.status == "active"

    def test_completing_the_short_in_house_path_never_touches_the_aircraft(self):
        aircraft = _aircraft(status="damaged")
        record = _record(aircraft, status="in_progress")
        record.status = "completed"

        record.save()

        aircraft.refresh_from_db()
        assert aircraft.status == "damaged"

    def test_the_status_change_time_is_stamped(self):
        record = _record()
        assert record.status_changed_at is not None  # al crear
        first = record.status_changed_at

        record.status = "in_progress"
        record.save()

        record.refresh_from_db()
        assert record.status_changed_at >= first


@pytest.mark.django_db(transaction=True)
class TestAFailedSaveLeavesNothingBehind:
    def test_no_orphan_history_row(self):
        record = _record()
        record.status = "in_progress"
        record.description = None  # viola NOT NULL: el guardado falla

        with pytest.raises(IntegrityError):
            record.save()

        assert _rows(record) == []
        assert MaintenanceRecord.objects.get(pk=record.pk).status == "pending"

    def test_the_aircraft_is_not_left_in_the_workshop(self):
        """Antes, la señal dejaba la aeronave en «mantención» y la mantención sin
        guardar: un avión fuera de servicio sin registro que lo explique."""
        aircraft = _aircraft()
        record = _record(aircraft)
        record.status = "sent"
        record.description = None  # el guardado falla

        with pytest.raises(IntegrityError):
            record.save()

        aircraft.refresh_from_db()
        assert aircraft.current_location != "maintenance"
        assert aircraft.status != "maintenance"
