"""Effectiveness verification of corrective actions (R7.6, ISO 10.2).

R6.2 made resolving an alert record its root cause, but resolving was still
terminal: nobody ever went back to ask whether the action actually worked. The
norm asks for exactly that second look, and without it a reason on record can
describe a fix that never held.

Reuses the shape of `check_monthly_review_deadline` (R6.5) rather than
inventing a mechanism: run daily, act on what is due, escalate what nobody
signed off. The difference is the trigger -- R6.5 acts on a calendar day (the
15th), this one acts on each alert's own due date, `resolved_at` +
`Alert.EFFECTIVENESS_DAYS` (30, set with the user on 2026-08-12).

This never resolves, reopens or verifies anything on its own: a machine
confirming that a corrective action was effective would be the exact opposite
of the evidence 10.2 asks for. It only reports what is waiting for a human.

`--dry-run` reports without sending mail. `--days N` overrides the window for
a one-off run without touching the model constant.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.models import Alert, NonConformity
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import record_job_run

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = (
        "Escalate corrective actions whose effectiveness nobody has verified "
        "within the review window."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without sending mail.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=(
                "Override the verification window in days (defaults to "
                "Alert.EFFECTIVENESS_DAYS)."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        window = options["days"] or Alert.EFFECTIVENESS_DAYS
        with record_job_run("check_alert_effectiveness") as run:
            rows, mailed = self._run(window, dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{len(rows)} awaiting "
                f"verification, {'mailed' if mailed else 'nothing to escalate'}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{len(rows)} corrective "
                f"action(s) awaiting verification."
            )
        )

    def _run(self, window, dry_run):
        today = timezone.localdate()
        due = (
            Alert.objects.filter(
                is_resolved=True,
                is_active=True,
                effectiveness_verified_at__isnull=True,
                effectiveness_due_date__lte=today,
            )
            .select_related("alert_rule", "content_type")
            .order_by("effectiveness_due_date")
        )
        rows = [
            {
                "entity": str(alert.content_object or _("Record unavailable")),
                "rule": alert.alert_rule.name,
                "resolved_on": (
                    alert.resolved_at.date().isoformat() if alert.resolved_at else "—"
                ),
                # The reason is the whole point of the follow-up: the reader has
                # to judge whether *that* action can be expected to have held.
                "reason": alert.resolution_reason or "—",
            }
            for alert in due
        ]
        # R7.6: non-conformities share the clock, so they share this job. A
        # second timer over the same question would mean two mails a manager
        # has to reconcile to know what is actually pending.
        findings_due = NonConformity.objects.filter(
            status=NonConformity.STATUS_CLOSED,
            is_active=True,
            effectiveness_verified_at__isnull=True,
            effectiveness_due_date__lte=today,
        ).order_by("effectiveness_due_date")
        rows += [
            {
                "entity": finding.title,
                "rule": finding.get_source_display(),
                "resolved_on": (
                    finding.closed_at.date().isoformat() if finding.closed_at else "—"
                ),
                "reason": finding.corrective_action or "—",
            }
            for finding in findings_due
        ]
        mailed = self._notify(rows, window, dry_run) if rows else False
        return rows, mailed

    def _notify(self, rows, window, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            # Same choice as R6.5: log and carry on rather than fail. A missing
            # group is a configuration gap, and crashing a daily timer over it
            # would hide every other thing this job reports.
            logger.warning(
                "alert_effectiveness_no_recipients",
                extra={
                    "recipient": "",
                    "item_count": len(rows),
                    "reason": "no_direccion",
                },
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{len(rows)} action(s) awaiting verification but no "
                    f"recipients in the {REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False

        context = {
            "rows": rows,
            "days": window,
            "base_url": settings.SITE_BASE_URL,
            "alert_path": f"{reverse('alert-list')}?is_resolved=true",
        }
        subject = _("AeroControl · %(count)s corrective action(s) to verify") % {
            "count": len(rows)
        }
        if not dry_run:
            EmailMessage(
                subject=subject,
                body=render_to_string(
                    "compliance/email/alert_effectiveness.txt", context
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "alert_effectiveness_sent",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(rows),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
