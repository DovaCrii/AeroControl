from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models import Document
from apps.compliance.storage import DocumentStorageError, get_document_storage


class Command(BaseCommand):
    help = "List or remove files for archived documents past the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-days", type=int, default=3650)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["older_than_days"])
        storage = get_document_storage()
        documents = Document.objects.filter(
            is_active=False, updated_at__lt=cutoff
        ).exclude(file_path="")
        for document in documents.iterator():
            try:
                exists = storage.exists(document.file_path)
            except DocumentStorageError:
                exists = False
            if not exists:
                self.stdout.write(f"Skipped unsafe or missing path: {document.pk}")
                continue
            self.stdout.write(
                f"{'Removing' if options['execute'] else 'Would remove'}: {document.file_path}"
            )
            if options["execute"]:
                storage.delete(document.file_path)
                document.file_path = ""
                document.save(update_fields=["file_path", "updated_at"])
