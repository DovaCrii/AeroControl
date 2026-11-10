"""LV-425: borra los PDF provisionales abandonados del ingreso.

Los ingresos nuevos ya hacen esta limpieza solos; el comando existe para correrla
a mano (`--dry-run` primero) o desde un timer, sin depender de que alguien suba
un PDF.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core import intake_pending
from apps.core.jobs import record_job_run


class Command(BaseCommand):
    help = "Delete abandoned provisional intake PDFs older than --hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=float,
            default=intake_pending.DEFAULT_MAX_AGE_HOURS,
            help="Minimum age in hours (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        if hours <= 0:
            raise CommandError("--hours must be greater than 0.")
        if options["dry_run"]:
            keys = intake_pending.purge_stale_pending(hours, dry_run=True)
            for key in keys:
                self.stdout.write(key)
            self.stdout.write(f"Dry run: {len(keys)} file(s) would be deleted.")
            return
        with record_job_run("purge_intake_pending") as run:
            removed = intake_pending.purge_stale_pending(hours)
            run["summary"] = f"{removed} file(s) removed (older than {hours:g} h)"
        self.stdout.write(self.style.SUCCESS(f"Purged {removed} stale intake file(s)."))
