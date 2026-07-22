import hashlib
import json
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore a verified SQLite backup to an explicit destination."

    def add_arguments(self, parser):
        parser.add_argument("backup", type=Path)
        parser.add_argument("destination", type=Path)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        backup = options["backup"].resolve()
        destination = options["destination"].resolve()
        manifest_path = backup.with_suffix(".json")
        if not backup.is_file() or not manifest_path.is_file():
            raise CommandError("Backup or manifest not found")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("Invalid backup manifest") from exc
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        if (
            manifest.get("backup") != backup.name
            or manifest.get("size") != backup.stat().st_size
            or manifest.get("sha256") != digest
        ):
            raise CommandError("Backup checksum does not match manifest")
        if destination.exists() and not options["force"]:
            raise CommandError("Destination exists; use --force to overwrite")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)
        self.stdout.write(self.style.SUCCESS(f"Backup restored: {destination}"))
