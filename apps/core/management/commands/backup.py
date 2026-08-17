import hashlib
import json
import sqlite3
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
        self._copy_database(source, destination)
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

    @staticmethod
    def _copy_database(source, destination):
        """LV-116: copia consistente aunque la aplicación esté escribiendo.

        Era `shutil.copy2`, que copia bytes sin saber nada de SQLite: si alguien
        guarda un documento mientras la copia avanza, el archivo resultante
        puede quedar a medio camino entre dos estados. Es el riesgo que la propia
        documentación de SQLite señala, y **no es teórico acá**: en `p340` el
        respaldo "de las 22:00" corre a las **18:00 hora de Chile** —el sistema
        está en UTC y Django sella los nombres en hora local—, o sea en plena
        jornada, con la app en uso. Encontrado el 2026-08-17 mirando por qué el
        archivo decía `180037` y systemd `22:00:37`.

        `Connection.backup()` es la API de respaldo en línea de SQLite: toma un
        punto consistente aunque haya escritores, sin bloquear la aplicación.

        Lo que **no** cambia: el respaldo sigue siendo un archivo suelto con su
        manifiesto, y `verify_backup` lo comprueba igual. Esto reduce la
        probabilidad de una copia rota; no reemplaza verificarla, porque un disco
        también se corrompe después.
        """
        # `sqlite3.connect` **crea** el archivo si no existe, así que sin esta
        # guarda una base ausente produciría un respaldo vacío y un `JobRun` en
        # verde -- exactamente el modo de fallo que este trabajo existe para
        # evitar. `copy2` fallaba solo; la API de respaldo hay que frenarla a
        # mano. Se mantiene `FileNotFoundError` porque es lo que el llamador ya
        # esperaba y lo que describe el problema.
        if not Path(source).is_file():
            raise FileNotFoundError(f"Database to back up not found: {source}")
        origin = sqlite3.connect(source)
        copy = sqlite3.connect(destination)
        try:
            origin.backup(copy)
        finally:
            copy.close()
            origin.close()
