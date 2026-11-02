"""LV-383 (PR 1 de 4): el ingreso a servicio técnico (`WorkshopIntake`) y la regla que
lo registra, `MaintenanceRecord.register_workshop_intake`.

Datos ficticios: OT `TEST-00001`, «Persona Ejemplo». `delivered_by` es un dato
personal y no debe aparecer en `__str__` ni en los logs.
"""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.maintenance.models import (
    MaintenanceHistory,
    MaintenanceRecord,
    WorkshopIntake,
    normalize_workshop_name,
    normalize_workshop_order,
)
from apps.registry.models import Aircraft, CostCenter

pytestmark = pytest.mark.django_db


def _aircraft(registration="CC-383"):
    return Aircraft.objects.create(
        registration=registration, type="Fixed", model="A", manufacturer="Maker"
    )


def _cost_center():
    return CostCenter.objects.create(name="Centro Ejemplo", code="CC-EJ")


def _data(**extra):
    data = {
        "workshop_name": "Taller Ejemplo",
        "workshop_order": "TEST-00001",
        "received_at": timezone.now(),
        "delivered_by": "Persona Ejemplo",
        "findings": "Gimbal con juego",
    }
    data.update(extra)
    return data


def _record(aircraft, status="pending"):
    return MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="Revision",
        status=status,
    )


def _steps(record):
    rows = MaintenanceHistory.objects.filter(record=record).order_by("sequence")
    return [(r.previous_status, r.new_status) for r in rows]


class TestRegisterWorkshopIntake:
    def test_happy_path_creates_record_history_and_moves_the_aircraft(self):
        aircraft = _aircraft()
        user = get_user_model().objects.create_user("ana", password="x")

        intake = MaintenanceRecord.register_workshop_intake(
            aircraft, _data(), user=user
        )

        record = intake.record
        assert record.maintenance_type == "unscheduled"
        assert record.status == "at_workshop"
        assert record.description == "Gimbal con juego"
        assert record.performed_by == "Taller Ejemplo"
        assert _steps(record) == [
            ("pending", "sent"),
            ("sent", "at_workshop"),
        ]
        assert (
            MaintenanceHistory.objects.get(
                record=record, new_status="sent"
            ).changed_by_user
            == user
        )
        aircraft.refresh_from_db()
        assert aircraft.current_location == "maintenance"
        assert aircraft.status == "maintenance"

    def test_empty_findings_use_a_generic_description(self):
        intake = MaintenanceRecord.register_workshop_intake(
            _aircraft(), _data(findings="")
        )
        assert intake.record.description

    def test_hangs_from_the_open_record_without_duplicating_it(self):
        aircraft = _aircraft()
        record = _record(aircraft)

        intake = MaintenanceRecord.register_workshop_intake(aircraft, _data())

        assert intake.record == record
        assert MaintenanceRecord.objects.filter(aircraft=aircraft).count() == 1
        record.refresh_from_db()
        assert record.status == "at_workshop"
        assert len(_steps(record)) == 2

    def test_explicit_existing_record_is_used(self):
        aircraft = _aircraft()
        _record(aircraft)
        chosen = _record(aircraft)

        intake = MaintenanceRecord.register_workshop_intake(
            aircraft, _data(), existing_record=chosen
        )

        assert intake.record == chosen

    def test_a_record_already_sent_is_not_walked_twice(self):
        aircraft = _aircraft()
        record = _record(aircraft)
        record.status = "sent"
        record.save()

        MaintenanceRecord.register_workshop_intake(aircraft, _data())

        record.refresh_from_db()
        assert record.status == "at_workshop"
        assert _steps(record) == [("pending", "sent"), ("sent", "at_workshop")]

    def test_a_record_already_at_the_workshop_gets_no_new_transitions(self):
        aircraft = _aircraft()
        record = _record(aircraft, status="at_workshop")

        MaintenanceRecord.register_workshop_intake(
            aircraft, _data(), existing_record=record
        )

        assert _steps(record) == []

    def test_a_record_with_an_intake_is_not_reused_for_a_second_one(self):
        aircraft = _aircraft()
        first = MaintenanceRecord.register_workshop_intake(aircraft, _data())

        second = MaintenanceRecord.register_workshop_intake(
            aircraft, _data(workshop_order="TEST-00002")
        )

        assert second.record != first.record

    def test_existing_record_of_another_aircraft_is_refused(self):
        other = _record(_aircraft("CC-384"))
        with pytest.raises(ValidationError):
            MaintenanceRecord.register_workshop_intake(
                _aircraft(), _data(), existing_record=other
            )

    def test_a_failed_intake_leaves_nothing_behind(self):
        aircraft = _aircraft()
        MaintenanceRecord.register_workshop_intake(aircraft, _data())
        other = _aircraft("CC-385")

        with pytest.raises(ValidationError):
            MaintenanceRecord.register_workshop_intake(other, _data())

        assert not MaintenanceRecord.objects.filter(aircraft=other).exists()
        other.refresh_from_db()
        assert other.status != "maintenance"

    def test_creating_a_record_straight_in_completed_still_moves_nothing(self):
        aircraft = _aircraft()
        _record(aircraft, status="completed")
        aircraft.refresh_from_db()
        assert aircraft.current_location != "maintenance"
        assert aircraft.status != "maintenance"


class TestConstraints:
    def _intake(self, **extra):
        record = _record(_aircraft(f"CC-{MaintenanceRecord.objects.count() + 400}"))
        values = {
            "record": record,
            "workshop_name": "Taller Ejemplo",
            "received_at": timezone.now(),
        }
        values.update(extra)
        return WorkshopIntake(**values)

    def test_cost_center_is_required_when_sent_by_a_cost_center(self):
        intake = self._intake(sent_by="cost_center")
        with pytest.raises(IntegrityError), transaction.atomic():
            intake.save()
        with pytest.raises(ValidationError) as exc:
            intake.full_clean()
        assert "sender_cost_center" in exc.value.message_dict

    @pytest.mark.parametrize("sent_by", ["head_office", "unknown"])
    def test_cost_center_must_be_empty_otherwise(self, sent_by):
        intake = self._intake(sent_by=sent_by, sender_cost_center=_cost_center())
        with pytest.raises(IntegrityError), transaction.atomic():
            intake.save()
        with pytest.raises(ValidationError) as exc:
            intake.full_clean()
        assert "sender_cost_center" in exc.value.message_dict

    def test_a_cost_center_with_the_matching_origin_is_valid(self):
        intake = self._intake(sent_by="cost_center", sender_cost_center=_cost_center())
        intake.full_clean()
        intake.save()

    def test_the_same_workshop_order_cannot_repeat(self):
        self._intake(workshop_order="TEST-00001").save()
        # Same workshop spelled differently + order with spaces and lower case.
        clash = self._intake(
            workshop_name="  TALLER  ejemplo ", workshop_order="test- 00001"
        )
        with pytest.raises(ValidationError) as exc:
            clash.full_clean()
        assert "workshop_order" in exc.value.message_dict
        with pytest.raises(IntegrityError), transaction.atomic():
            clash.save()

    def test_the_clean_message_does_not_name_the_other_record(self):
        first = self._intake(workshop_order="TEST-00001")
        first.save()
        clash = self._intake(workshop_order="TEST-00001")
        with pytest.raises(ValidationError) as exc:
            clash.full_clean()
        text = str(exc.value)
        assert str(first.record_id) not in text and "CC-" not in text

    def test_same_order_at_another_workshop_is_fine(self):
        self._intake(workshop_order="TEST-00001").save()
        other = self._intake(workshop_name="Otro Taller", workshop_order="TEST-00001")
        other.full_clean()
        other.save()

    def test_an_archived_intake_does_not_block_the_order(self):
        first = self._intake(workshop_order="TEST-00001")
        first.save()
        first.is_active = False
        first.save()
        self._intake(workshop_order="TEST-00001").save()

    def test_an_empty_order_can_repeat(self):
        self._intake(workshop_order="").save()
        again = self._intake(workshop_order="")
        again.full_clean()
        again.save()
        assert WorkshopIntake.objects.filter(workshop_order="").count() == 2


class TestNormalization:
    def test_workshop_key_drops_accents_case_and_extra_spaces(self):
        assert (
            normalize_workshop_name("  Taller   Técnico  ÁÑO ") == "taller tecnico ano"
        )

    def test_workshop_order_is_uppercase_without_spaces(self):
        assert normalize_workshop_order(" test- 00 001\t") == "TEST-00001"

    def test_save_stores_both_normalized_values(self):
        intake = MaintenanceRecord.register_workshop_intake(
            _aircraft(),
            _data(workshop_name="Taller  Técnico", workshop_order=" test 00001 "),
        )
        intake.refresh_from_db()
        assert intake.workshop_key == "taller tecnico"
        assert intake.workshop_order == "TEST00001"


class TestPersonalData:
    def test_str_does_not_include_the_delivering_person(self):
        intake = MaintenanceRecord.register_workshop_intake(_aircraft(), _data())
        assert "Persona Ejemplo" not in str(intake)

    def test_registering_logs_nothing_with_the_delivering_person(self, caplog):
        with caplog.at_level(logging.DEBUG):
            MaintenanceRecord.register_workshop_intake(_aircraft(), _data())
        assert "Persona Ejemplo" not in caplog.text
