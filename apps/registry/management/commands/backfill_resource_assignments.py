"""Create OPS-1 assignments from the denormalized cost_center FK where missing.

The operational data was imported by setting `Operator.cost_center` /
`Aircraft.cost_center` directly, without the OperatorAssignment /
AircraftAssignment rows OPS-1 treats as the source of truth. The result: the
cost-center list counts resources (from the FK) while the contract detail's
Equipo/Flota tabs, the entity timelines and the movement log (all read from the
assignment tables) show nothing.

This reconciles them: one active assignment per resource that has a cost center
but no active assignment to it. Idempotent. Re-run it after any bulk import
(e.g. chapter1_import) that sets the FK directly.

Creating the assignment fires the OPS-1 signal, but the FK already matches the
target, so the signal is a no-op -- no fabricated movement-log entry.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    Operator,
    OperatorAssignment,
)


class Command(BaseCommand):
    help = "Backfill OPS-1 assignments from the cost_center FK where missing."

    @transaction.atomic
    def handle(self, *args, **options):
        operators = self._backfill(Operator, OperatorAssignment, "operator")
        aircraft = self._backfill(Aircraft, AircraftAssignment, "aircraft")
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {operators} operator and {aircraft} aircraft assignments."
            )
        )

    @staticmethod
    def _backfill(resource_model, assignment_model, field):
        created = 0
        for resource in resource_model.objects.filter(
            is_active=True, cost_center__isnull=False
        ):
            already = assignment_model.objects.filter(
                is_active=True,
                status__in=assignment_model.ACTIVE_STATUSES,
                cost_center_id=resource.cost_center_id,
                **{f"{field}_id": resource.pk},
            ).exists()
            if already:
                continue
            assignment_model.objects.create(
                status="active",
                start_date=resource.created_at.date(),
                cost_center=resource.cost_center,
                **{field: resource},
            )
            created += 1
        return created
