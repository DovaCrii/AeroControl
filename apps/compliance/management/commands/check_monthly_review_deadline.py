"""Mid-month compliance review deadline (R6.5).

`check_monthly_records` (LV-30) creates the pending review on the last day of
the month and notifies Dirección once. The internal procedure also requires a
follow-up on the 15th of the next month: anything still `pending` at that
point (nobody signed it off) gets escalated in a second email, so a review
does not quietly sit unaddressed until someone happens to open the monthly-
review page.

This never creates or changes a MonthlyComplianceReview -- it only reports
whatever check_monthly_records already created. A review missing entirely
(that job never ran) is not this command's problem to fix; it would show up
as zero pending rows here, not as a false "all clear".

Runs daily via a timer and acts only on the 15th. `--period YYYY-MM` targets
a specific month's review (the month being reviewed, not the day it runs on)
for a rerun or a test; `--force` runs off the 15th; `--dry-run` reports
without sending mail.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.models import MonthlyComplianceReview
from apps.compliance.monthly import (
    flights_in_month,
    is_review_deadline_day,
    month_start,
    previous_month_start,
    records_in_month,
)
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = (
        "On the 15th, escalate to Dirección any monthly compliance review "
        "still pending from last month."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help="Reviewed month YYYY-MM (defaults to the month before this one).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when today is not the 15th.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without sending mail.",
        )

    def handle(self, *args, **options):
        period = self._target_period(options)
        if period is None:
            self.stdout.write("Not the 15th; nothing to do (use --force or --period).")
            return

        dry_run = options["dry_run"]
        with record_job_run("check_monthly_review_deadline") as run:
            rows, mailed = self._run(period, dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{period:%Y-%m}: "
                f"{len(rows)} pending, {'mailed' if mailed else 'nothing to escalate'}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{period:%Y-%m}: {len(rows)} "
                f"review(s) still pending."
            )
        )

    def _target_period(self, options):
        if options.get("period"):
            try:
                return datetime.strptime(options["period"], "%Y-%m").date()
            except ValueError as exc:
                raise CommandError("--period must be YYYY-MM.") from exc
        today = timezone.localdate()
        if is_review_deadline_day(today) or options["force"]:
            return previous_month_start(today)
        return None

    def _run(self, period, dry_run):
        period_start = month_start(period)
        pending = list(
            MonthlyComplianceReview.objects.filter(
                period=period_start,
                status=MonthlyComplianceReview.STATUS_PENDING,
                is_active=True,
            )
            .select_related("cost_center")
            .order_by("cost_center__code")
        )
        rows = [
            {
                "code": review.cost_center.code,
                "name": review.cost_center.name,
                "flights": flights_in_month(review.cost_center, period_start),
                "records": records_in_month(review.cost_center, period_start),
            }
            for review in pending
        ]
        mailed = self._notify(period_start, rows, dry_run) if rows else False
        return rows, mailed

    def _notify(self, period_start, rows, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            logger.warning(
                "monthly_review_deadline_no_recipients",
                extra={
                    "recipient": "",
                    "item_count": len(rows),
                    "reason": "no_direccion",
                },
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{len(rows)} review(s) still pending but no recipients in the "
                    f"{REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False
        context = {
            "period": period_start.strftime("%Y-%m"),
            "rows": rows,
            "base_url": settings.SITE_BASE_URL,
            "review_path": reverse("monthly-review"),
        }
        subject = _("AeroControl · monthly review deadline reminder %(period)s") % {
            "period": period_start.strftime("%Y-%m")
        }
        if not dry_run:
            EmailMessage(
                subject=subject,
                body=render_to_string(
                    "compliance/email/monthly_review_deadline.txt", context
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "monthly_review_deadline_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(rows),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
