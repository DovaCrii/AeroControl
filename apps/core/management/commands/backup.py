import shutil
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a timestamped SQLite backup."

    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        destination_dir = Path(
            __import__("decouple").config(
                "BACKUPS_DIR", default=str(source.parent / "backups")
            )
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = (
            destination_dir / f"aero_ops_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
        )
        shutil.copy2(source, destination)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {destination}"))
