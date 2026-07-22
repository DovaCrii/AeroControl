from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models import Document


class Command(BaseCommand):
    help = "List or remove files for archived documents past the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-days", type=int, default=3650)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["older_than_days"])
        root = Path(settings.DOCUMENTS_ROOT).resolve()
        documents = Document.objects.filter(
            is_active=False, updated_at__lt=cutoff
        ).exclude(file_path="")
        for document in documents.iterator():
            path = (root / document.file_path).resolve()
            if root not in path.parents or not path.is_file():
                self.stdout.write(f"Skipped unsafe or missing path: {document.pk}")
                continue
            self.stdout.write(f"{'Removing' if options['execute'] else 'Would remove'}: {path}")
            if options["execute"]:
                path.unlink()
                document.file_path = ""
                document.save(update_fields=["file_path", "updated_at"])
