"""LV-82: the maintenance record's progress as a stepper, and its history.

The interesting part is not the stepper -- it is that maintenance has **two**
paths, and drawing them as one line would promise an in-house repair a trip to a
workshop it is never making. LV-72 deliberately left out records whose status is
not a progression; this one *is* a progression, it just forks.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceHistory, MaintenanceRecord
from apps.registry.models import Aircraft


def _record(**kwargs):
    aircraft = Aircraft.objects.create(
        registration=kwargs.pop("registration", "CC-AAA"),
        type="RPA",
        model="M3",
        manufacturer="DJI",
    )
    return MaintenanceRecord.objects.create(
        aircraft=aircraft, maintenance_type="preventive", **kwargs
    )


@pytest.mark.django_db
class TestWhichPath:
    def test_a_new_record_shows_the_short_path(self):
        """Most maintenance is resolved in-house (R5.1's own reasoning), and a
        record at "pending" has not diverged yet."""
        record = _record(status="pending")

        assert [step["code"] for step in record.status_steps()] == [
            "pending",
            "in_progress",
            "completed",
        ]

    def test_being_at_a_workshop_switches_the_path(self):
        record = _record(status="at_workshop")

        codes = [step["code"] for step in record.status_steps()]
        assert codes == MaintenanceRecord.WORKSHOP_FLOW
        assert "in_progress" not in codes

    def test_a_completed_record_still_shows_the_path_it_took(self):
        """Read from the history, not from the current status: once completed,
        both paths look identical from the status alone."""
        record = _record(status="pending")
        for status in ("sent", "at_workshop", "finished", "in_transit", "completed"):
            record.status = status
            record.save()

        assert [step["code"] for step in record.status_steps()] == (
            MaintenanceRecord.WORKSHOP_FLOW
        )

    def test_an_in_house_record_completed_stays_on_the_short_path(self):
        record = _record(status="pending")
        for status in ("in_progress", "completed"):
            record.status = status
            record.save()

        assert [step["code"] for step in record.status_steps()] == [
            "pending",
            "in_progress",
            "completed",
        ]

    def test_the_step_it_stands_on_is_the_current_one(self):
        record = _record(status="in_progress")

        assert [step["state"] for step in record.status_steps()] == [
            "done",
            "current",
            "pending",
        ]

    def test_an_unsaved_record_does_not_query_its_history(self):
        """`status_flow` guards on `pk`: a record built in memory has no history
        to ask about, and asking would raise."""
        aircraft = Aircraft.objects.create(
            registration="CC-BBB", type="RPA", model="M3", manufacturer="DJI"
        )

        unsaved = MaintenanceRecord(
            aircraft=aircraft, maintenance_type="preventive", status="pending"
        )

        assert unsaved.status_flow() == MaintenanceRecord.IN_HOUSE_FLOW


@pytest.mark.django_db
class TestHistory:
    def test_the_labels_are_translatable(self):
        """R2.5's defect, still open here until LV-82: without `choices` Django
        never generates get_new_status_display, so the fiche printed the raw
        codes ("at_workshop") inside a Spanish page."""
        record = _record(status="pending")
        record.status = "at_workshop"
        record.save()

        entry = MaintenanceHistory.objects.get(record=record)
        assert entry.get_new_status_display() != entry.new_status

    def test_rows_are_ordered_by_their_own_sequence(self):
        """`created_at` ties: timezone.now() can return the identical value
        across rapid successive saves, and then the fiche prints its own
        history backwards."""
        record = _record(status="pending")
        for status in ("in_progress", "completed"):
            record.status = status
            record.save()

        assert [entry.new_status for entry in record.history.all()] == [
            "completed",
            "in_progress",
        ]


@pytest.mark.django_db
class TestOnThePage:
    def test_the_fiche_renders_the_stepper_instead_of_raw_codes(self):
        record = _record(status="at_workshop")
        record.status = "finished"
        record.save()

        content = (
            login_as("view_maintenancerecord")
            .get(reverse("maintenance-detail", args=[record.pk]))
            .content.decode()
        )

        assert "status-step" in content
        # The raw code must not reach the page anywhere in the history table.
        assert "at_workshop" not in content
