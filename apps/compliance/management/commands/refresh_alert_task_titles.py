from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import Alert
from apps.workboard.models import KanbanTask


class Command(BaseCommand):
    help = (
        "Rewrite follow-up task titles that were stored before the models got "
        "__str__ methods (they read 'Qualification object (uuid)')."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the changes. Without it, only report what would change.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        alert_ct = ContentType.objects.get_for_model(Alert)
        tasks = KanbanTask.objects.filter(
            source_content_type=alert_ct, title__contains=" object ("
        )
        changed = 0
        for task in tasks:
            alert = task.source_object
            if alert is None:
                continue
            new_title = f"{alert.alert_rule.name}: {alert.content_object}"
            if new_title == task.title:
                continue
            self.stdout.write(f"{task.title!r} -> {new_title!r}")
            if options["apply"]:
                task.title = new_title
                task.save(update_fields=["title", "updated_at"])
            changed += 1
        verb = "Updated" if options["apply"] else "Would update"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} task titles."))
