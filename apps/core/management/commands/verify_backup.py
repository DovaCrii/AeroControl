"""Comprobar que un respaldo sirve — a mano antes de restaurar, o solo cada día.

**Dos modos, un comando.** Con una ruta (`verify_backup <archivo>`) es lo que
siempre fue: verifica **ese** respaldo y **falla ruidosamente** si algo no
cuadra, que es lo que hace falta cuando alguien está por restaurar y quiere que
el comando se plante antes de tocar nada. Sin argumentos (`LV-115`) toma el
**último** respaldo, lo verifica y avisa por correo a Dirección, callando cuando
está sano: es la mitad automatizable del criterio 4 de salida a 1.0.

Se dejaron en el mismo comando a propósito. Son la misma pregunta —"¿este
respaldo serviría?"— con dos audiencias, y separarlos habría significado dos
implementaciones de la verificación que se desincronizan: la peor forma de este
defecto es que el chequeo automático diga "sano" con una regla más floja que la
del que corre a mano.

`LV-115` además refuerza **qué** se comprueba. El modo con ruta miraba tamaño y
`sha256`, y eso prueba que el archivo **no cambió desde que se escribió**, no que
sea una base usable: `backup` copia el `.sqlite3` con `shutil.copy2` mientras la
aplicación puede estar escribiendo —el caso que SQLite documenta como riesgoso—,
así que un respaldo roto de nacimiento tiene un checksum perfectamente válido.
Ahora los dos modos **abren** el archivo y lo consultan.

El ensayo completo de restauración —restaurar en otra máquina y mirar la app
funcionando— sigue siendo humano y sigue haciendo falta.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.core.backups import latest_backup, load_manifest, verify
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run
from apps.core.mail import warn_undelivered_mail

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = (
        "Verify a SQLite backup against its manifest. Without arguments, checks "
        "the latest one and warns Dirección when it would not restore."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "backup",
            type=Path,
            nargs="?",
            help="Backup to verify. Omit to check the most recent one.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Scheduled mode: report without sending mail.",
        )

    def handle(self, *args, **options):
        if options.get("backup"):
            self._verify_one(options["backup"])
            return
        self._verify_latest(options["dry_run"])

    def _verify_one(self, path):
        """Modo manual: falla ruidosamente. Quien está por restaurar necesita
        que el comando se plante, no un correo."""
        backup = load_manifest(Path(path).resolve())
        if backup is None:
            raise CommandError("Backup or manifest not found")
        problems = verify(backup)
        if problems:
            raise CommandError(
                "; ".join(str(problem["message"]) for problem in problems)
            )
        self.stdout.write(self.style.SUCCESS(f"Backup verified: {backup['path']}"))

    def _verify_latest(self, dry_run):
        with record_job_run("verify_backup") as run:
            backup = latest_backup()
            if backup is None:
                # No tener respaldo es peor que tener uno malo, así que se
                # reporta igual en vez de salir en silencio por "no hay nada
                # que verificar".
                problems = [
                    {
                        "code": "no_backup",
                        "message": _("There is no backup with a readable manifest"),
                    }
                ]
                name = "—"
            else:
                problems = verify(backup)
                name = backup["name"]
            mailed = self._notify(name, problems, dry_run) if problems else False
            run["mailed"] = mailed and not dry_run  # LV-119
            run["summary"] = f"{'[dry-run] ' if dry_run else ''}{name}: " + (
                f"{len(problems)} problem(s){', mailed' if mailed else ''}"
                if problems
                else "restorable"
            )
        if problems:
            for problem in problems:
                self.stdout.write(self.style.ERROR(f"{name}: {problem['message']}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"{name}: restorable."))

    def _notify(self, name, problems, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            logger.warning(
                "backup_verification_no_recipients",
                extra={"recipient": "", "item_count": len(problems)},
            )
            self.stdout.write(
                self.style.WARNING(
                    f"No recipients in the {REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False
        if not dry_run:
            warn_undelivered_mail(self)  # LV-119
            EmailMessage(
                subject=_("AeroControl · the latest backup did not verify"),
                body=render_to_string(
                    "core/email/backup_verification.txt",
                    {
                        "name": name,
                        "problems": problems,
                        "base_url": settings.SITE_BASE_URL,
                    },
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "backup_verification_reported",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(problems),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
