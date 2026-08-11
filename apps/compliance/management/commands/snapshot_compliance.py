"""Record the documentary compliance totals for one date (R7.7, ISO 9.1.1).

Exists so the report can show a **trend**. `build_compliance_report` evaluates
`valid`/`expired`/`due_*` always "as of today" no matter what period is asked
for, so comparing period against period reads "no change" on those counters by
construction (found while doing R6.4). Storing the totals per day turns the
comparison into real history.

Reads its numbers from `build_compliance_report`, the same function the screen,
the spreadsheet and the executive email use -- so a snapshot can never disagree
with the report it is supposed to be the history of.

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
from apps.compliance.reports import build_compliance_report
from apps.core.jobs import record_job_run
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
        report = build_compliance_report()
        # The report identifies cost centers by code (it is a display
        # structure); the snapshot needs the FK, so resolve them in one query
        # rather than one per row.
        by_code = {
            cost_center.code: cost_center
            for cost_center in CostCenter.objects.filter(is_active=True)
        }

        rows = []
        for row in report["by_cost_center"]:
            cost_center = by_code.get(row["code"])
            if cost_center is None:
                # An archived center can still appear in a report built before
                # it was archived; skip rather than guess.
                continue
            rows.append((cost_center, row))
        # The consolidated row (cost_center=None) is not the sum of the rows
        # above when a doc_type filter is involved -- here it is unfiltered, so
        # the report's own totals are authoritative.
        rows.append((None, report["totals"]))

        if dry_run:
            for cost_center, values in rows:
                scope = cost_center.code if cost_center else "TOTAL"
                self.stdout.write(
                    f"[dry-run] {scope}: {values['valid']}/{values['total']} "
                    f"valid, {values['expired']} expired"
                )
            return len(rows)

        for cost_center, values in rows:
            ComplianceSnapshot.objects.update_or_create(
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
        logger.info(
            "compliance_snapshot_written",
            extra={"item_count": len(rows), "snapshot_date": day.isoformat()},
        )
        return len(rows)
