import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.anonymized_snapshot import (
    SNAPSHOT_VERSION,
    anonymize_value,
    get_snapshot_models,
    is_generic_content_type,
    is_inside_repo,
    json_default,
    model_label,
    MODEL_LABELS,
)


class Command(BaseCommand):
    help = "Export a relationship-preserving, anonymized snapshot outside the repository."

    def add_arguments(self, parser):
        parser.add_argument("output", type=Path)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        output = options["output"].resolve()
        if is_inside_repo(output, self.get_repo_root()):
            raise CommandError("Snapshot output must be outside the repository")
        if output.exists() and not options["force"]:
            raise CommandError(f"Output already exists: {output}")

        payload = {
            "version": SNAPSHOT_VERSION,
            "kind": "aerocontrol-anonymized-snapshot",
            "models": {},
            "excluded": [
                "auth.User",
                "core.AuditEvent",
                "core.ImportBatch",
                "core.TenantMembership",
                "workboard.KanbanBoardAccess",
            ],
        }
        for label, model in get_snapshot_models():
            rows = []
            for index, instance in enumerate(model.objects.order_by("pk"), start=1):
                fields = {}
                for field in model._meta.concrete_fields:
                    if field.name == "id":
                        continue
                    value = getattr(instance, field.attname)
                    if field.is_relation:
                        if value is None:
                            fields[field.name] = None
                        elif field.name == "source_content_type":
                            fields[field.name] = None
                        elif is_generic_content_type(field):
                            content_type = field.remote_field.model.objects.get(pk=value)
                            fields[field.name] = (
                                f"{content_type.app_label}.{content_type.model}"
                            )
                        else:
                            remote_label = model_label(field.remote_field.model)
                            fields[field.name] = (
                                str(value) if remote_label in MODEL_LABELS else None
                            )
                    else:
                        fields[field.name] = anonymize_value(
                            field.name, value, label, index
                        )
                fields["_source_id"] = str(instance.pk)
                if label == "compliance.Document":
                    fields["file_path"] = ""
                rows.append(fields)
            payload["models"][label] = rows

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
            encoding="utf-8",
        )
        counts = {label: len(rows) for label, rows in payload["models"].items()}
        self.stdout.write(self.style.SUCCESS(f"Anonymized snapshot written: {output}"))
        self.stdout.write(json.dumps({"models": counts}, ensure_ascii=False))

    @staticmethod
    def get_repo_root():
        from django.conf import settings

        return Path(settings.BASE_DIR).resolve()
