import logging
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

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
        today = timezone.localdate()
        # One query instead of an EXISTS per candidate record: the nightly run
        # grew linearly with history, holding SQLite's write lock the while.
        open_alert_keys = set(
            Alert.objects.filter(is_resolved=False, is_active=True).values_list(
                "alert_rule_id", "object_id"
            )
        )
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
                # Bounded: without a floor this rescanned every open record
                # since the beginning of time, forever. A record stuck in an
                # open status alerted while young and that alert stays open
                # (alerts never auto-expire), so only a rule created more than
                # a year after the record would miss it.
                # Terminal statuses across the watchable models: a completed
                # maintenance, a denied permit, a reviewed monthly compliance
                # (LV-30: completed or non_compliant -- the reviewer acted).
                records = records.exclude(
                    status__in=("completed", "denied", "non_compliant")
                ).filter(created_at__gte=timezone.now() - timedelta(days=365))
            for record in records:
                if (rule.pk, record.pk) in open_alert_keys:
                    duplicates += 1
                    continue
                value = getattr(record, field, "")
                # Atomic per alert: if the process dies between creating the
                # alert and its follow-up task, the dedupe above would count
                # the orphan alert as a duplicate on the next run and the task
                # would never be created.
                with transaction.atomic():
                    alert = Alert.objects.create(
                        alert_rule=rule,
                        content_type=content_type,
                        object_id=record.pk,
                        message=f"{rule.name}: {record} ({field}: {value})",
                    )
                    task = alert.ensure_follow_up_task()
                generated += 1
                if task is not None:
                    tasks_created += 1
        return generated, duplicates, tasks_created
