"""Daily flight duty limit (R7.5, ISO 45001 6.1.2 / 8.1.2).

Pilot fatigue is one of the hazards the field IPER has to control, and a duty
limit is the control the audit guide names. `FlightRecord` already carried
everything needed -- date, departure, arrival, pilot -- so this needs no new
data: it groups by (pilot, date) and compares against
`selectors.DAILY_FLIGHT_LIMIT` (8 hours, set with the user on 2026-08-12).

Reports yesterday by default, because a day is only complete once it is over;
run at 08:00 on the day itself it would report a partial total and read like an
all-clear. `--date YYYY-MM-DD` targets a specific day, `--dry-run` reports
without sending mail.

This only reports. It never edits or rejects a flight record: the record is
written *after* the flight, so refusing it would not un-fly the day -- it would
only leave the excess unrecorded, destroying the evidence the clause exists to
produce.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run
from apps.core.mail import warn_undelivered_mail
from apps.operations.selectors import (
    DAILY_FLIGHT_LIMIT,
    format_duration,
    pilots_over_daily_limit,
)

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = "Report pilots whose logged flight time for a day exceeded the daily limit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            help="Day to check, YYYY-MM-DD (defaults to yesterday).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without sending mail.",
        )

    def handle(self, *args, **options):
        day = self._target_day(options)
        dry_run = options["dry_run"]
        with record_job_run("check_flight_duty_limit") as run:
            rows, mailed = self._run(day, dry_run)
            run["mailed"] = mailed and not dry_run  # LV-119
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{day.isoformat()}: "
                f"{len(rows)} over limit, "
                f"{'mailed' if mailed else 'nothing to report'}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{day.isoformat()}: {len(rows)} "
                f"pilot(s) over the daily flight limit."
            )
        )

    def _target_day(self, options):
        if options.get("date"):
            try:
                return datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date must be YYYY-MM-DD.") from exc
        # Yesterday: a day is only complete once it is over.
        return timezone.localdate() - timedelta(days=1)

    def _run(self, day, dry_run):
        rows = [
            {
                "pilot": str(pilot),
                "total": format_duration(total),
                "over_by": format_duration(total - DAILY_FLIGHT_LIMIT),
            }
            for pilot, total in pilots_over_daily_limit(day)
        ]
        mailed = self._notify(day, rows, dry_run) if rows else False
        return rows, mailed

    def _notify(self, day, rows, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            # Same choice as R6.5/R7.6a: log and carry on. A configuration gap
            # must not take down a daily timer.
            logger.warning(
                "duty_limit_no_recipients",
                extra={
                    "recipient": "",
                    "item_count": len(rows),
                    "reason": "no_direccion",
                },
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{len(rows)} pilot(s) over the limit but no recipients in "
                    f"the {REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False

        context = {
            "day": day.isoformat(),
            "rows": rows,
            "limit": format_duration(DAILY_FLIGHT_LIMIT),
            "base_url": settings.SITE_BASE_URL,
        }
        subject = _("AeroControl · daily flight limit exceeded on %(day)s") % {
            "day": day.isoformat()
        }
        if not dry_run:
            warn_undelivered_mail(self)  # LV-119
            EmailMessage(
                subject=subject,
                body=render_to_string("operations/email/duty_limit.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "duty_limit_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(rows),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
