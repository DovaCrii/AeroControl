"""OPS-1 data migration: split each active Assignment into per-resource ones.

Every active `Assignment` with a cost center becomes one `OperatorAssignment`
and one `AircraftAssignment` over the same period, and the resource's
denormalized `cost_center` is aligned to its current assignment. Signals do not
fire during migrations, so the denormalization is set explicitly here.

Idempotent (safe to re-run) and non-destructive: the old Assignment rows are
left untouched, and reversing is a no-op so manually created per-resource
assignments are never deleted. Take a database backup before deploying, as the
plan flags — this touches real operational data.
"""

from datetime import date

from django.db import migrations, models

_STATUS_MAP = {
    "planned": "planned",
    "confirmed": "active",
    "completed": "ended",
    "cancelled": "cancelled",
}


def _current(model, field, resource_id):
    today = date.today()
    return (
        model.objects.filter(
            is_active=True,
            status__in=["planned", "active"],
            **{f"{field}_id": resource_id},
        )
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=today))
        .order_by("-start_date")
        .first()
    )


def forward(apps, schema_editor):
    Assignment = apps.get_model("registry", "Assignment")
    OperatorAssignment = apps.get_model("registry", "OperatorAssignment")
    AircraftAssignment = apps.get_model("registry", "AircraftAssignment")
    Operator = apps.get_model("registry", "Operator")
    Aircraft = apps.get_model("registry", "Aircraft")

    for assignment in Assignment.objects.filter(is_active=True):
        if not assignment.cost_center_id:
            continue  # a cost-center-less assignment cannot anchor a resource
        status = _STATUS_MAP.get(assignment.status, "active")
        common = {
            "cost_center_id": assignment.cost_center_id,
            "start_date": assignment.start_date,
            "end_date": assignment.end_date,
            "status": status,
            "purpose": assignment.purpose,
        }
        if not OperatorAssignment.objects.filter(
            operator_id=assignment.operator_id,
            cost_center_id=assignment.cost_center_id,
            start_date=assignment.start_date,
        ).exists():
            OperatorAssignment.objects.create(
                operator_id=assignment.operator_id, **common
            )
        if not AircraftAssignment.objects.filter(
            aircraft_id=assignment.aircraft_id,
            cost_center_id=assignment.cost_center_id,
            start_date=assignment.start_date,
        ).exists():
            AircraftAssignment.objects.create(
                aircraft_id=assignment.aircraft_id, **common
            )

    for operator in Operator.objects.all():
        current = _current(OperatorAssignment, "operator", operator.pk)
        if current and operator.cost_center_id != current.cost_center_id:
            operator.cost_center_id = current.cost_center_id
            operator.save(update_fields=["cost_center", "updated_at"])

    for aircraft in Aircraft.objects.all():
        current = _current(AircraftAssignment, "aircraft", aircraft.pk)
        if current and aircraft.cost_center_id != current.cost_center_id:
            aircraft.cost_center_id = current.cost_center_id
            aircraft.save(update_fields=["cost_center", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0011_aircraftassignment_operatorassignment_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
