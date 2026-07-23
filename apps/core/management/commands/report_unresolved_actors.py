from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.maintenance.models import MaintenanceHistory
from apps.operations.models import PermissionHistory
from apps.workboard.models import KanbanTask


class Command(BaseCommand):
    help = "Report historical actor labels that could not be resolved to users."

    def handle(self, *args, **options):
        usernames = set(get_user_model().objects.values_list("username", flat=True))
        sources = (
            ("maintenance", MaintenanceHistory.objects.values_list("changed_by", flat=True)),
            ("operations", PermissionHistory.objects.values_list("changed_by", flat=True)),
            ("workboard", KanbanTask.objects.values_list("created_by", flat=True)),
        )
        total = 0
        for name, labels in sources:
            unresolved = sorted({label for label in labels if label and label not in usernames})
            total += len(unresolved)
            self.stdout.write(f"{name}: {len(unresolved)} unresolved actor labels")
            for label in unresolved:
                self.stdout.write(f"  - {label}")
        self.stdout.write(f"total: {total}")
