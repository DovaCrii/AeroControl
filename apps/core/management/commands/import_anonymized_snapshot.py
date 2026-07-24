import io
import json
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.compliance.storage import get_document_storage
from apps.core.anonymized_snapshot import (
    SNAPSHOT_VERSION,
    get_snapshot_models,
    model_label,
)


class Command(BaseCommand):
    help = "Import an anonymized snapshot into an empty database."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source = options["source"].resolve()
        if not source.is_file():
            raise CommandError(f"Snapshot does not exist: {source}")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("Invalid snapshot JSON") from exc
        if payload.get("version") != SNAPSHOT_VERSION or payload.get("kind") != "aerocontrol-anonymized-snapshot":
            raise CommandError("Unsupported snapshot format")
        models = dict(get_snapshot_models())
        unknown = set(payload.get("models", {})) - set(models)
        if unknown:
            raise CommandError(f"Unsupported models in snapshot: {sorted(unknown)}")
        for label, model in models.items():
            if model.objects.exists():
                raise CommandError(f"Target database is not empty: {label}")
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Snapshot validation passed"))
            return

        source_to_target = {label: {} for label in models}
        created = {label: [] for label in models}
        with transaction.atomic():
            for label, model in models.items():
                for raw in payload.get("models", {}).get(label, []):
                    source_id = raw.get("_source_id")
                    if not source_id:
                        raise CommandError(f"Missing _source_id in {label}")
                    data = self.build_data(model, raw, source_to_target)
                    instance = model.objects.create(**data)
                    source_to_target[label][source_id] = str(instance.pk)
                    created[label].append(instance)

            self.resolve_generic_objects(created, source_to_target)
            self.create_synthetic_documents(created.get("compliance.Document", []))

        counts = {label: len(rows) for label, rows in created.items() if rows}
        self.stdout.write(self.style.SUCCESS("Anonymized snapshot imported"))
        self.stdout.write(json.dumps({"models": counts}, ensure_ascii=False))

    def build_data(self, model, raw, source_to_target):
        data = {}
        for field in model._meta.concrete_fields:
            if field.name == "id":
                continue
            value = raw.get(field.name)
            if field.name in {"source_content_type", "source_object_id"}:
                data[field.name] = None
            elif field.name == "content_type" and value:
                app_label, model_name = value.split(".", 1)
                data[field.attname] = ContentType.objects.get_by_natural_key(
                    app_label, model_name
                ).pk
            elif field.is_relation:
                if value is None:
                    data[field.attname] = None
                else:
                    remote_label = model_label(field.remote_field.model)
                    try:
                        data[field.attname] = source_to_target[remote_label][str(value)]
                    except KeyError as exc:
                        raise CommandError(
                            f"Unresolved reference {remote_label}:{value}"
                        ) from exc
            else:
                if value is not None:
                    value = field.to_python(value)
                data[field.name] = value
        return data

    def resolve_generic_objects(self, created, source_to_target):
        for label in ("compliance.Document", "compliance.Alert"):
            for instance in created.get(label, []):
                if not instance.content_type_id or not instance.object_id:
                    continue
                target_label = model_label(instance.content_type.model_class())
                target_id = source_to_target.get(target_label, {}).get(str(instance.object_id))
                if target_id:
                    instance.object_id = target_id
                    instance.save(update_fields=["object_id", "updated_at"])

    def create_synthetic_documents(self, documents):
        storage = get_document_storage()
        for document in documents:
            key = f"synthetic/document/{document.pk}.txt"
            storage.save(key, io.BytesIO(b"AeroControl synthetic test document\n"))
            document.file_path = key
            document.save(update_fields=["file_path", "updated_at"])
