import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify a SQLite backup against its JSON manifest."

    def add_arguments(self, parser):
        parser.add_argument("backup", type=Path)

    def handle(self, *args, **options):
        backup = options["backup"].resolve()
        manifest_path = backup.with_suffix(".json")
        if not backup.is_file() or not manifest_path.is_file():
            raise CommandError("Backup or manifest not found")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("Invalid backup manifest") from exc
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        if manifest.get("backup") != backup.name:
            raise CommandError("Manifest does not match backup filename")
        if manifest.get("size") != backup.stat().st_size:
            raise CommandError("Backup size does not match manifest")
        if manifest.get("sha256") != digest:
            raise CommandError("Backup checksum does not match manifest")
        self.stdout.write(self.style.SUCCESS(f"Backup verified: {backup}"))
