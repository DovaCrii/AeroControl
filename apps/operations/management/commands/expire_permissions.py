"""LV-83: close a flight permit once its authorization window has run out.

Decided with the user on 2026-08-13. Until now nothing moved a permit by date:
the only non-human writer was the `"system"` fallback in `apps/core/signals.py`,
which is what gets recorded when someone edits outside a view (admin, shell,
importer) -- so a permit whose validity ended last month still read "Aprobado",
as if it were live.

**Expired is not completed**, and that distinction is the whole design:

- `completed` means the authorized work was flown *and* the signed DGAC
  authorization is on file -- `RequireDgacPermitPdfMixin` refuses the transition
  without it (LV-51/LV-64/R2.4). A job that auto-completed permits would walk
  straight through that guard and let this app's status outrun the real
  paperwork.
- `expired` only means the window closed. A permit can expire having flown
  nothing at all, and `on_time_execution` exists precisely to count those.

Runs as a daily job, never as a computed property on the page: a status that
only exists while somebody is looking at a screen cannot be filtered, reported
or alerted on -- which is the point of closing it.

Deliberately does **not** touch `denied` (it never became an authorization) or
`completed` (already closed, and re-closing it would erase that it was flown).
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.jobs import record_job_run
from apps.operations.models import FlightPermission

logger = logging.getLogger("aerocontrol.notifications")

# Recorded as the actor on every row this job writes. Not the generic "system"
# fallback: an auditor reading the trace should see *what* closed the permit,
# not merely that no human did.
ACTOR = "expire_permissions"


class Command(BaseCommand):
    help = "Mark flight permits as expired once their validity has run out."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be expired without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = timezone.localdate()
        with record_job_run("expire_permissions") as run:
            permits = self._due(today)
            folios = [permit.internal_folio for permit in permits]
            if not dry_run:
                self._expire(permits)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{today.isoformat()}: "
                f"{len(folios)} expired"
            )
        for folio in folios:
            self.stdout.write(f"  {folio}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{len(folios)} permit(s) expired."
            )
        )

    @staticmethod
    def _due(today):
        """Active permits whose window closed and that are still open.

        `valid_until` is inclusive -- the permit is good *through* that day --
        so the comparison is strictly less than today, not less-or-equal.
        """
        return list(
            FlightPermission.objects.filter(
                is_active=True,
                valid_until__lt=today,
                status__in=[
                    FlightPermission.STATUS_REQUESTED,
                    FlightPermission.STATUS_APPROVED,
                ],
            ).order_by("valid_until")
        )

    @staticmethod
    def _expire(permits):
        for permit in permits:
            # One save per permit rather than a bulk `update()`: the trace is
            # written by a pre_save signal, and `queryset.update()` does not
            # fire signals -- the permits would change state with no history
            # row, which is the one thing this must not do.
            with transaction.atomic():
                permit.status = FlightPermission.STATUS_EXPIRED
                permit._changed_by = ACTOR
                permit.save(update_fields=["status", "updated_at"])
            logger.info("permission_expired", extra={"folio": permit.internal_folio})
