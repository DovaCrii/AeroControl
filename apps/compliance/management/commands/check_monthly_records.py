"""End-of-month compliance sweep (LV-30).

Runs daily via a timer and acts only on the last day of the month (when
tomorrow is a different month): for every cost center that flew that month it
ensures a `MonthlyComplianceReview` in `pending` and emails the reviewer group
(Dirección) a flights-vs-records summary. The pending review is what the alert
rule turns into a live alert until the reviewer signs it off.

Idempotent: an existing review for the (cost center, period) is left as it is,
so a rerun -- or a review already marked -- is never reset. `--period YYYY-MM`
targets a specific month and `--force` runs off the last day, both for reruns
and testing; `--dry-run` reports without creating reviews or sending mail.
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
    cost_centers_that_flew,
    flights_in_month,
    is_last_day_of_month,
    month_start,
    records_in_month,
)
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run
from apps.core.mail import warn_undelivered_mail

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = (
        "At month-end, create pending monthly compliance reviews and notify Dirección."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help="Target month YYYY-MM (defaults to the month that closes today).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when today is not the last day of the month.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without creating reviews or sending mail.",
        )

    def handle(self, *args, **options):
        period = self._target_period(options)
        if period is None:
            self.stdout.write(
                "Not the last day of the month; nothing to do (use --force or --period)."
            )
            return

        dry_run = options["dry_run"]
        with record_job_run("check_monthly_records") as run:
            created, rows, mailed = self._run(period, dry_run)
            run["mailed"] = mailed and not dry_run  # LV-119
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{period:%Y-%m}: "
                f"{len(rows)} cost centers, {created} reviews created, "
                f"{'mailed' if mailed else 'no recipients'}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{period:%Y-%m}: {len(rows)} cost "
                f"centers, {created} reviews {'would be ' if dry_run else ''}created."
            )
        )

    def _target_period(self, options):
        if options.get("period"):
            try:
                return datetime.strptime(options["period"], "%Y-%m").date()
            except ValueError as exc:
                raise CommandError("--period must be YYYY-MM.") from exc
        today = timezone.localdate()
        if is_last_day_of_month(today) or options["force"]:
            return today
        return None

    def _run(self, period, dry_run):
        period_start = month_start(period)
        created = 0
        rows = []
        for cost_center in cost_centers_that_flew(period):
            flights = flights_in_month(cost_center, period)
            records = records_in_month(cost_center, period)
            if dry_run:
                review = MonthlyComplianceReview.objects.filter(
                    cost_center=cost_center, period=period_start
                ).first()
                status = (
                    review.status if review else MonthlyComplianceReview.STATUS_PENDING
                )
            else:
                review, was_created = MonthlyComplianceReview.objects.get_or_create(
                    cost_center=cost_center, period=period_start
                )
                created += int(was_created)
                status = review.status
            rows.append(
                {
                    "code": cost_center.code,
                    "flights": flights,
                    "records": records,
                    "status": dict(MonthlyComplianceReview.STATUS_CHOICES)[status],
                }
            )
        mailed = self._notify(period_start, rows, dry_run) if rows else False
        return created, rows, mailed

    def _notify(self, period_start, rows, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            # Not a failure: the reviews (and their alerts) are the durable
            # signal. Report the gap and carry on, like send_alert_digest.
            logger.warning(
                "monthly_review_no_recipients",
                extra={
                    "recipient": "",
                    "item_count": len(rows),
                    "reason": "no_direccion",
                },
            )
            self.stdout.write(
                self.style.WARNING(
                    f"No recipients in the {REPORT_RECIPIENTS!r} group; reviews "
                    "created but no email sent."
                )
            )
            return False
        context = {
            "period": period_start.strftime("%Y-%m"),
            "rows": rows,
            "base_url": settings.SITE_BASE_URL,
            "review_path": reverse("monthly-review"),
        }
        subject = _("AeroControl · monthly records review %(period)s") % {
            "period": period_start.strftime("%Y-%m")
        }
        if not dry_run:
            warn_undelivered_mail(self)  # LV-119
            EmailMessage(
                subject=subject,
                body=render_to_string("compliance/email/monthly_review.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "monthly_review_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(rows),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
