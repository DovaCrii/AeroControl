import logging
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import models

from apps.compliance.models import Alert, AlertRule
from apps.compliance.watchables import resolve_model, watchable_fields
from apps.core.jobs import record_job_run

logger = logging.getLogger("compliance.alerts")


class Command(BaseCommand):
    help = "Generate unresolved compliance alerts for configured rules."

    def handle(self, *args, **options):
        with record_job_run("generate_alerts") as run:
            generated, duplicates, tasks_created = self._generate()
            run["summary"] = (
                f"{generated} alerts, {duplicates} duplicates skipped, "
                f"{tasks_created} follow-up tasks"
            )
        self.stdout.write(
            f"Generated {generated} alerts, skipped {duplicates} duplicates, "
            f"created {tasks_created} follow-up tasks"
        )

    def _generate(self):
        generated = 0
        duplicates = 0
        tasks_created = 0
        today = date.today()
        for rule in AlertRule.objects.filter(enabled=True, is_active=True):
            model = resolve_model(rule.entity_type)
            if model is None:
                reason = "unknown_entity_type"
            elif rule.field_to_watch not in watchable_fields(model):
                reason = "unknown_field_to_watch"
            else:
                reason = None
            if reason is not None:
                self.stdout.write(
                    self.style.WARNING(f"Skipped invalid rule: {rule.name}")
                )
                logger.warning(
                    "invalid_alert_rule_skipped",
                    extra={
                        "rule_id": str(rule.pk),
                        "rule_name": rule.name,
                        "entity_type": rule.entity_type,
                        "field_to_watch": rule.field_to_watch,
                        "reason": reason,
                    },
                )
                continue
            content_type = ContentType.objects.get_for_model(model)
            field = rule.field_to_watch
            records = model.objects.filter(is_active=True)
            # The field is known to be watchable at this point, so branch on its
            # actual type rather than guessing from the name.
            if isinstance(model._meta.get_field(field), models.DateField):
                records = records.filter(
                    **{
                        f"{field}__isnull": False,
                        f"{field}__lte": today
                        + timedelta(days=rule.days_before_expiry),
                    }
                )
            else:  # a `status` field with choices
                records = records.exclude(status__in=("completed", "denied"))
            for record in records:
                if Alert.objects.filter(
                    alert_rule=rule,
                    content_type=content_type,
                    object_id=record.pk,
                    is_resolved=False,
                    is_active=True,
                ).exists():
                    duplicates += 1
                    continue
                value = getattr(record, field, "")
                alert = Alert.objects.create(
                    alert_rule=rule,
                    content_type=content_type,
                    object_id=record.pk,
                    message=f"{rule.name}: {record} ({field}: {value})",
                )
                generated += 1
                if alert.ensure_follow_up_task() is not None:
                    tasks_created += 1
        return generated, duplicates, tasks_created
