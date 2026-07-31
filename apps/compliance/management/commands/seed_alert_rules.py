"""Seed the recommended AlertRule set for a DGAC RPAS operation.

Idempotent by `name` (get_or_create): safe to run more than once, and a rerun
after a rule is tuned in the UI (days_before_expiry, enabled, Kanban target)
leaves that edit alone -- it only creates rules that are still missing. See
docs/compliance-setup.md, "Paso 3".

The two essential rules cover the whole document catalog and the DGAC flight
permits; `--with-optional` also seeds the qualification and maintenance rules.
Kanban task creation is left off on purpose: seed the board with
``init_dgac_board`` before turning it on.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import AlertRule

# (name, entity_type, field_to_watch, days_before_expiry)
ESSENTIAL_RULES = [
    ("Documentos por vencer", "compliance.document", "expiry_date", 30),
    ("Permisos de vuelo por vencer", "operations.flightpermission", "valid_until", 30),
]

OPTIONAL_RULES = [
    ("Habilitaciones por vencer", "registry.qualification", "expiry_date", 30),
    ("Mantenimiento programado", "maintenance.maintenancerecord", "scheduled_date", 15),
]


class Command(BaseCommand):
    help = "Create the recommended AlertRule set for a DGAC RPAS operation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-optional",
            action="store_true",
            help="Also seed the qualification and maintenance rules.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rules = list(ESSENTIAL_RULES)
        if options["with_optional"]:
            rules += OPTIONAL_RULES

        created_count = 0
        for name, entity_type, field_to_watch, days_before_expiry in rules:
            _obj, created = AlertRule.objects.get_or_create(
                name=name,
                defaults={
                    "entity_type": entity_type,
                    "field_to_watch": field_to_watch,
                    "days_before_expiry": days_before_expiry,
                    "enabled": True,
                    "create_kanban_task": False,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(rules)} alert rules ({created_count} created)."
            )
        )
