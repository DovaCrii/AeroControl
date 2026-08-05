"""Notify each operator of their own DGAC vigencias about to lapse (LV-29).

Unlike ``send_alert_digest`` (which mails the cost-center responsible a summary
of the whole contract), this mails each operator directly about the validities
they personally have to renew: their DGAC credential and their qualifications
expiring within the window (already-lapsed ones included -- flying on an expired
credential is the most urgent case, not the least).

Only operators with an ``email`` on file are reachable; the rest are reported
and skipped, never a crash. ``--dry-run`` prints without sending. Documented as
an optional timer in docs/dev/scheduled-operations.md.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.jobs import record_job_run
from apps.registry.models import Operator, Qualification

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = (
        "Email each operator their DGAC credential/qualification expiries (<=30 days)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Look-ahead window in days (default 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be sent without sending any email.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        days = options["days"]
        with record_job_run("notify_expiring_credentials") as run:
            sent, skipped, items = self._run(days, dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}"
                f"{sent} notices, {items} items, {skipped} unreachable"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would send' if dry_run else 'Sent'} {sent} notices "
                f"({items} items); {skipped} operators had expiries but no email."
            )
        )

    def _run(self, days, dry_run):
        today = timezone.localdate()
        cutoff = today + timedelta(days=days)
        sent = skipped = total_items = 0

        for operator in Operator.objects.filter(is_active=True):
            items = self._items_for(operator, today, cutoff)
            if not items:
                continue
            if not operator.email:
                skipped += 1
                logger.warning(
                    "credential_notice_recipient_missing",
                    extra={
                        "recipient": "",
                        "item_count": len(items),
                        "send_result": "skipped",
                        "reason": "operator_without_email",
                    },
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"{operator.full_name}: {len(items)} expiring items but no "
                        "email on file; skipped."
                    )
                )
                continue

            subject = _("AeroControl · your DGAC validities are expiring")
            if dry_run:
                self.stdout.write(
                    f"[dry-run] {operator.email} <- {operator.full_name}: "
                    f"{len(items)} items"
                )
            else:
                body = render_to_string(
                    "registry/email/credential_notice.txt",
                    {"operator": operator, "items": items},
                )
                EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[operator.email],
                ).send()
            sent += 1
            total_items += len(items)
            logger.info(
                "credential_notice_sent",
                extra={
                    "recipient": operator.email,
                    "item_count": len(items),
                    "send_result": "dry_run" if dry_run else "sent",
                },
            )
        return sent, skipped, total_items

    @staticmethod
    def _items_for(operator, today, cutoff):
        """This operator's expiring items: the credential field plus each active
        qualification, all with expiry on or before the cutoff (past-due kept)."""
        items = []
        if operator.credential_expiry and operator.credential_expiry <= cutoff:
            items.append(
                {
                    "label": _("DGAC credential"),
                    "date": operator.credential_expiry,
                    "overdue": operator.credential_expiry < today,
                }
            )
        quals = (
            Qualification.objects.filter(
                operator=operator,
                is_active=True,
                expiry_date__isnull=False,
                expiry_date__lte=cutoff,
            )
            .select_related("qualification_type")
            .order_by("expiry_date")
        )
        for qual in quals:
            items.append(
                {
                    "label": str(qual.qualification_type),
                    "date": qual.expiry_date,
                    "overdue": qual.expiry_date < today,
                }
            )
        items.sort(key=lambda item: item["date"])
        return items
