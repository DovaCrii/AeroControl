"""LV-401: respaldo de los documentos (PDF) de `DOCUMENTS_ROOT`.

`backup` copia sólo la base; los PDF firmados viven en disco aparte y en la VM
no tenían respaldo alguno. Este comando deja un `tar.gz` completo con un
manifiesto JSON al lado (cantidad de archivos, bytes, `sha256` del tar, fecha)
y aplica la retención por **cantidad** (`--keep`, por defecto `BACKUP_KEEP`).

Se excluye `workshop-intake-pending/`: son subidas del taller aún sin revisar,
temporales por diseño, y no son evidencia documental.
"""

import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.backups import (
    DOCS_PATTERN,
    DOCS_PREFIX,
    DOCS_SUFFIX,
    apply_retention,
    docs_manifest_path,
)
from apps.core.jobs import record_job_run
from apps.core.management.commands.backup import backups_dir

EXCLUDED_TOP_LEVEL = "workshop-intake-pending"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Create a timestamped tar.gz backup of the documents folder."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            type=int,
            default=None,
            help="Backups to keep (default: settings.BACKUP_KEEP, 14).",
        )

    def handle(self, *args, **options):
        keep = options["keep"]
        if keep is None:
            keep = getattr(settings, "BACKUP_KEEP", 14)
        if keep < 1:
            raise CommandError("--keep must be at least 1.")
        with record_job_run("backup_documents") as run:
            destination, manifest, count, size = self._create_backup()
            removed = apply_retention(backups_dir(), DOCS_PATTERN, keep)
            run["summary"] = (
                f"{destination.name} ({count} files, {size} bytes); "
                f"{len(removed)} old removed"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Documents backup created: {destination} ({manifest})")
        )

    def _create_backup(self):
        root = Path(settings.DOCUMENTS_ROOT)
        if not root.is_dir():
            raise CommandError(f"Documents folder not found: {root}")
        destination_dir = backups_dir()
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now()
        destination = (
            destination_dir / f"{DOCS_PREFIX}{stamp:%Y%m%d_%H%M%S}{DOCS_SUFFIX}"
        )
        partial = destination.with_name(destination.name + ".partial")
        skip_dir = destination_dir.resolve()
        count = 0
        total = 0
        try:
            with tarfile.open(partial, "w:gz") as archive:
                for path in sorted(root.rglob("*")):
                    relative = path.relative_to(root)
                    if relative.parts[0] == EXCLUDED_TOP_LEVEL:
                        continue
                    # Si BACKUPS_DIR cuelga de DOCUMENTS_ROOT, no se respalda a
                    # sí mismo.
                    if skip_dir == path.resolve() or skip_dir in path.resolve().parents:
                        continue
                    archive.add(path, arcname=relative.as_posix(), recursive=False)
                    if path.is_file():
                        count += 1
                        total += path.stat().st_size
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        manifest = docs_manifest_path(destination)
        manifest.write_text(
            json.dumps(
                {
                    "kind": "documents",
                    "backup": destination.name,
                    "source": str(root),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "files": count,
                    "bytes": total,
                    "size": destination.stat().st_size,
                    "sha256": _sha256(destination),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return destination, manifest, count, total
