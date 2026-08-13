"""LV-90: which statuses close a record, declared by the model that owns them.

`generate_alerts` used to hold a literal tuple mixing three models'
vocabularies, so every new terminal status depended on somebody remembering that
one line -- and forgetting it fails **silently**, as alerts that keep firing for
something already closed. It had bitten twice by the time this was written.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, MonthlyComplianceReview
from apps.compliance.watchables import (
    WATCHABLE_MODELS,
    resolve_model,
    terminal_statuses,
    watchable_fields,
)
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


def _rule(entity_type, name="status rule"):
    return AlertRule.objects.create(
        name=name,
        entity_type=entity_type,
        field_to_watch="status",
        days_before_expiry=0,
        enabled=True,
    )


def _alerts_for(model):
    return Alert.objects.filter(
        content_type=ContentType.objects.get_for_model(model), is_active=True
    )


class TestEveryWatchableModelDeclaresThem:
    def test_a_watchable_status_field_comes_with_its_terminal_statuses(self):
        """The guard that keeps this from drifting back: a model whose `status`
        can be watched has to say where that status stops, or the alert engine
        is silently deciding for it."""
        missing = []
        for key in WATCHABLE_MODELS:
            model = resolve_model(key)
            if "status" in watchable_fields(model) and not terminal_statuses(model):
                missing.append(key)

        assert missing == [], (
            "these watchable models expose `status` but declare no "
            f"TERMINAL_STATUSES: {missing}"
        )

    def test_every_declared_terminal_status_is_a_real_choice(self):
        """A typo would exclude nothing and, again, say nothing."""
        wrong = {}
        for key in WATCHABLE_MODELS:
            model = resolve_model(key)
            if "status" not in watchable_fields(model):
                continue
            valid = {code for code, _label in model._meta.get_field("status").choices}
            unknown = terminal_statuses(model) - valid
            if unknown:
                wrong[key] = unknown

        assert wrong == {}


@pytest.mark.django_db
class TestTheEngineReadsThem:
    def test_a_retired_aircraft_stops_raising_alerts(self):
        """Never in the old literal list, which only knew the permit's and the
        maintenance record's vocabularies -- so a rule watching an aircraft's
        status alerted on retired airframes forever. `fleet_availability`
        already excluded them from its denominator for the same reason."""
        retired = Aircraft.objects.create(
            registration="CC-RET",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            status="retired",
        )
        active = Aircraft.objects.create(
            registration="CC-ACT",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            status="active",
        )
        _rule("registry.aircraft")

        call_command("generate_alerts")

        alerted = set(_alerts_for(Aircraft).values_list("object_id", flat=True))
        assert alerted == {active.pk}
        assert retired.pk not in alerted

    def test_a_completed_maintenance_record_raises_none(self):
        aircraft = Aircraft.objects.create(
            registration="CC-MNT", type="RPA", model="M3", manufacturer="DJI"
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="preventive", status="completed"
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="preventive", status="pending"
        )
        _rule("maintenance.maintenancerecord")

        call_command("generate_alerts")

        assert _alerts_for(MaintenanceRecord).count() == 1

    @pytest.mark.parametrize("status", ["denied", "completed", "expired"])
    def test_every_closed_permit_status_is_terminal(self, status):
        cost_center = CostCenter.objects.create(code="CC-T")
        FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="photogrammetry",
            valid_from=TODAY - timedelta(days=10),
            valid_until=TODAY - timedelta(days=1),
            location="Site",
            status=status,
        )
        _rule("operations.flightpermission")

        call_command("generate_alerts")

        assert not _alerts_for(FlightPermission).exists()

    def test_a_reviewed_month_is_terminal(self):
        cost_center = CostCenter.objects.create(code="CC-M")
        MonthlyComplianceReview.objects.create(
            cost_center=cost_center,
            period=TODAY.replace(day=1),
            status=MonthlyComplianceReview.STATUS_COMPLETED,
        )
        _rule("compliance.monthlycompliancereview")

        call_command("generate_alerts")

        assert not _alerts_for(MonthlyComplianceReview).exists()
