import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.report_views import build_report_workbook_bytes
from apps.compliance.reports import build_compliance_report
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run

logger = logging.getLogger("aerocontrol.notifications")

PERIOD_DAYS = {"week": 7, "month": 30}

# KPIs compared against the previous period. "lower_is_better" decides whether a
# rise is reported as an improvement or a regression, so the wording cannot
# contradict the number.
COMPARED_KPIS = [
    ("valid_pct", _("Valid documents (%)"), False),
    ("expired", _("Expired documents"), True),
    ("due_30", _("Expiring within 30 days"), True),
]


class Command(BaseCommand):
    help = (
        "Email the executive compliance report for a period, compared with the "
        "previous one, with the XLSX attached."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            choices=sorted(PERIOD_DAYS),
            default="week",
            help="Length of the reporting period. Default: week.",
        )
        parser.add_argument(
            "--to",
            nargs="*",
            help=f"Recipients. Defaults to the {REPORT_RECIPIENTS} group.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be sent without sending anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        period = options["period"]
        with record_job_run("send_executive_report") as run:
            recipients = self._recipients(options["to"])
            current, previous, comparison = self._build(period)
            if dry_run:
                self._print_preview(period, current, comparison, recipients)
            else:
                self._send(period, current, comparison, recipients)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{period}, "
                f"{len(recipients)} recipient(s), "
                f"{current['totals']['total']} documents"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would send' if dry_run else 'Sent'} the {period} executive "
                f"report to {len(recipients)} recipient(s)."
            )
        )

    def _recipients(self, explicit):
        if explicit:
            return list(explicit)
        emails = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not emails:
            raise CommandError(
                f"No recipients: pass --to, or add users with an email to the "
                f"{REPORT_RECIPIENTS!r} group."
            )
        return emails

    @staticmethod
    def _build(period):
        days = PERIOD_DAYS[period]
        # Same timezone as the report's own period bounds; see reports.py.
        end = timezone.localdate()
        start = end - timedelta(days=days)
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days)

        current = build_compliance_report(start=start, end=end)
        previous = build_compliance_report(start=previous_start, end=previous_end)

        comparison = []
        for key, label, lower_is_better in COMPARED_KPIS:
            now = current["totals"][key]
            before = previous["totals"][key]
            delta = round(now - before, 1)
            if delta == 0:
                direction = "flat"
            elif (delta < 0) == lower_is_better:
                direction = "better"
            else:
                direction = "worse"
            comparison.append(
                {
                    "label": label,
                    "current": now,
                    "previous": before,
                    "delta": delta,
                    "direction": direction,
                }
            )
        # Resolution time is only meaningful per period, so it is compared apart
        # from the expiry counters above.
        comparison.append(
            {
                "label": _("Alerts resolved in the period"),
                "current": current["resolution"]["resolved_count"],
                "previous": previous["resolution"]["resolved_count"],
                "delta": (
                    current["resolution"]["resolved_count"]
                    - previous["resolution"]["resolved_count"]
                ),
                "direction": "flat",
            }
        )
        return current, previous, comparison

    @staticmethod
    def _context(period, report, comparison):
        return {
            "period_label": _("week") if period == "week" else _("month"),
            "report": report,
            "comparison": comparison,
            "base_url": settings.SITE_BASE_URL,
        }

    def _send(self, period, report, comparison, recipients):
        context = self._context(period, report, comparison)
        subject = _("AeroControl · executive compliance report (%(period)s)") % {
            "period": context["period_label"]
        }
        message = EmailMultiAlternatives(
            subject=subject,
            body=render_to_string("compliance/email/executive_report.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        message.attach_alternative(
            render_to_string("compliance/email/executive_report.html", context),
            "text/html",
        )
        message.attach(
            f"aerocontrol-cumplimiento-{report['generated_on'].isoformat()}.xlsx",
            build_report_workbook_bytes(report),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        message.send()
        # Counts and recipients only; the report body is never logged.
        logger.info(
            "executive_report_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": report["totals"]["total"],
                "send_result": "sent",
            },
        )

    def _print_preview(self, period, report, comparison, recipients):
        self.stdout.write(f"[dry-run] period={period} to={', '.join(recipients)}")
        totals = report["totals"]
        self.stdout.write(
            f"[dry-run] {totals['valid']}/{totals['total']} valid "
            f"({totals['valid_pct']}%), {totals['expired']} expired"
        )
        for row in comparison:
            self.stdout.write(
                f"[dry-run]   {row['label']}: {row['current']} "
                f"(prev {row['previous']}, {row['delta']:+}) {row['direction']}"
            )
        logger.info(
            "executive_report_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": totals["total"],
                "send_result": "dry_run",
            },
        )
