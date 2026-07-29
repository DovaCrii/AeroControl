import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from decouple import config
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.jobs import record_job_run


def backups_dir():
    """Directory where backups + manifests live. Shared with the admin panel
    (B5.2) so both read the exact same location."""
    source = Path(settings.DATABASES["default"]["NAME"])
    return Path(config("BACKUPS_DIR", default=str(source.parent / "backups")))


class Command(BaseCommand):
    help = "Create a timestamped SQLite backup."

    def handle(self, *args, **options):
        with record_job_run("backup") as run:
            destination, manifest = self._create_backup()
            run["summary"] = f"{destination.name} ({destination.stat().st_size} bytes)"
        self.stdout.write(
            self.style.SUCCESS(f"Backup created: {destination} (manifest: {manifest})")
        )

    def _create_backup(self):
        source = Path(settings.DATABASES["default"]["NAME"])
        destination_dir = backups_dir()
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = (
            destination_dir / f"aero_ops_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
        )
        shutil.copy2(source, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest = destination.with_suffix(".json")
        manifest.write_text(
            json.dumps(
                {
                    "backup": destination.name,
                    "source": str(source),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "size": destination.stat().st_size,
                    "sha256": digest,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return destination, manifest
