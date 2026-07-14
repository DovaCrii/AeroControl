from datetime import date, timedelta

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.compliance.models import Alert, AlertRule


class Command(BaseCommand):
    help = "Generate unresolved compliance alerts for configured rules."

    def handle(self, *args, **options):
        generated = 0
        duplicates = 0
        today = date.today()
        for rule in AlertRule.objects.filter(enabled=True, is_active=True):
            model = self._find_model(rule.entity_type)
            if model is None or not hasattr(model, rule.field_to_watch):
                self.stdout.write(self.style.WARNING(f"Skipped invalid rule: {rule.name}"))
                continue
            content_type = ContentType.objects.get_for_model(model)
            field = rule.field_to_watch
            records = model.objects.filter(is_active=True)
            if field.endswith("expiry_date") or field.endswith("date"):
                records = records.filter(**{f"{field}__isnull": False, f"{field}__lte": today + timedelta(days=rule.days_before_expiry)})
            elif field == "status":
                records = records.exclude(status__in=("completed", "denied"))
            else:
                continue
            for record in records:
                if Alert.objects.filter(alert_rule=rule, content_type=content_type, object_id=record.pk, is_resolved=False, is_active=True).exists():
                    duplicates += 1
                    continue
                value = getattr(record, field, "")
                Alert.objects.create(
                    alert_rule=rule, content_type=content_type, object_id=record.pk,
                    message=f"{rule.name}: {record} ({field}: {value})",
                )
                generated += 1
        self.stdout.write(f"Generated {generated} alerts, skipped {duplicates} duplicates")

    @staticmethod
    def _find_model(entity_type):
        target = entity_type.replace("_", "").replace("-", "").lower()
        for model in apps.get_models():
            if model.__name__.replace("_", "").lower() == target:
                return model
        return None
