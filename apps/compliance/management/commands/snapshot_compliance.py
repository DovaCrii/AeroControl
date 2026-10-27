"""Record the documentary compliance totals for one date (R7.7, ISO 9.1.1).

Exists so the report can show a **trend**. `build_compliance_report` evaluates
`valid`/`expired`/`due_*` always "as of today" no matter what period is asked
for, so comparing period against period reads "no change" on those counters by
construction (found while doing R6.4). Storing the totals per day turns the
comparison into real history.

`documentary_rows`, the function `build_compliance_report` uses for the screen,
the spreadsheet and the executive email -- so a snapshot can never disagree
with the report it is supposed to be the history of.

LV-372 (F-08): writes one row per cost center (with its tenant) and one
consolidated row **per tenant**; codes are only unique within a tenant.

Idempotent: rerunning for the same date **overwrites** that date instead of
adding rows, so a job that fires twice cannot corrupt a trend. `--date` targets
a specific day (for a backfill); `--dry-run` reports without writing.
"""

import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.compliance.models import ComplianceSnapshot
from apps.compliance.reports import documentary_rows
from apps.core.jobs import record_job_run
from apps.core.models import OperationalTenant
from apps.registry.models import CostCenter

logger = logging.getLogger("compliance.alerts")


class Command(BaseCommand):
    help = "Store today's compliance totals so the report can show a trend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            help="Target date YYYY-MM-DD (defaults to today). For backfills.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the totals without writing anything.",
        )

    def handle(self, *args, **options):
        day = self._target_date(options)
        dry_run = options["dry_run"]
        with record_job_run("snapshot_compliance") as run:
            written = self._run(day, dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{day:%Y-%m-%d}: {written} row(s)"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{day:%Y-%m-%d}: "
                f"{written} snapshot row(s)."
            )
        )

    def _target_date(self, options):
        if options.get("date"):
            try:
                return datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date must be YYYY-MM-DD.") from exc
        # Same timezone as the report's own period bounds; see reports.py.
        return timezone.localdate()

    @transaction.atomic
    def _run(self, day, dry_run):
        # LV-372 (F-08): una consolidada **por empresa**, y cada fila por faena con su empresa.
        # Antes el comando sumaba todas las empresas en una sola fila bajo la empresa por defecto
        # y buscaba la faena por `code`, que sólo es único dentro de una empresa.
        today = timezone.localdate()
        written = 0
        for tenant in OperationalTenant.objects.filter(is_active=True).order_by("name"):
            centers = CostCenter.objects.filter(is_active=True, tenant=tenant).order_by(
                "code"
            )
            pairs, totals = documentary_rows(centers, None, today)
            # The consolidated row is unfiltered, so the sum of the centers is
            # authoritative (the doc_type filter is the only thing that would
            # make the two differ, and it is not involved here).
            rows = [*pairs, (None, totals)]
            written += len(rows)
            for cost_center, values in rows:
                if dry_run:
                    scope = cost_center.code if cost_center else "TOTAL"
                    self.stdout.write(
                        f"[dry-run] {scope}: {values['valid']}/{values['total']} "
                        f"valid, {values['expired']} expired"
                    )
                    continue
                ComplianceSnapshot.objects.update_or_create(
                    tenant=tenant,
                    date=day,
                    cost_center=cost_center,
                    defaults={
                        "total": values["total"],
                        "valid": values["valid"],
                        "expired": values["expired"],
                        "due_7": values["due_7"],
                        "due_15": values["due_15"],
                        "due_30": values["due_30"],
                        "is_active": True,
                    },
                )
        if not dry_run:
            logger.info(
                "compliance_snapshot_written",
                extra={"item_count": written, "snapshot_date": day.isoformat()},
            )
        return written
