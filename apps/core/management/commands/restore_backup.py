import hashlib
import json
import sqlite3
from pathlib import Path

from django.conf import settings
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
        live = Path(settings.DATABASES["default"]["NAME"]).resolve()
        is_live = destination == live
        if (destination.exists() or is_live) and not options["force"]:
            raise CommandError(
                "Destination is the configured live database; use --force "
                "after stopping the service (sudo systemctl stop aerocontrol)"
                if is_live
                else "Destination exists; use --force to overwrite"
            )
        if is_live:
            self.stdout.write(
                self.style.WARNING(
                    "Restoring over the live database: the 'aerocontrol' service "
                    "must be stopped first (sudo systemctl stop aerocontrol) and "
                    "started again afterwards."
                )
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        # SQLite's online backup API, not `copy2`: the live database runs in WAL
        # mode, and a byte copy leaves the previous `-wal`/`-shm` beside the new
        # file, where SQLite replays them over the restored pages and damages it.
        origin = sqlite3.connect(f"{backup.as_uri()}?mode=ro", uri=True)
        target = sqlite3.connect(destination)
        try:
            origin.backup(target)
        finally:
            target.close()
            origin.close()
        self.stdout.write(self.style.SUCCESS(f"Backup restored: {destination}"))
