import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.digest import (
    BUCKETS,
    archived_centers_with_active_dependents,
    build_digest,
    cost_centers_to_notify,
)
from apps.core.jobs import record_job_run

logger = logging.getLogger("aerocontrol.notifications")

BUCKET_TITLES = {
    # Distinct from the "Overdue" badge in the alert list: this labels a section
    # of several items, so it needs plural wording of its own.
    "overdue": (_("Already expired"), "#c0392b"),
    "due_7": (_("Due within 7 days"), "#d97706"),
    "due_15": (_("Due within 15 days"), "#b7791f"),
    "due_30": (_("Due within 30 days"), "#2a7f78"),
}


class Command(BaseCommand):
    help = (
        "Email each cost center's responsible operator a summary of documents "
        "and qualifications expiring within 30 days, grouped by urgency."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be sent without sending any email.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with record_job_run("send_alert_digest") as run:
            sent, skipped, items = self._run(dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}"
                f"{sent} digests, {items} items, {skipped} skipped"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would send' if dry_run else 'Sent'} {sent} digests "
                f"({items} items); skipped {skipped} cost centers."
            )
        )

    def _run(self, dry_run):
        today = timezone.localdate()
        sent = skipped = total_items = 0
        # Archived centers fall out of the loop below by design, but falling
        # out silently while they still have active operators or aircraft is a
        # compliance blind spot: their documents stop being watched with no
        # trace. Report it every run until the dependents are reassigned.
        for center, operators, aircraft in archived_centers_with_active_dependents():
            logger.warning(
                "digest_archived_center_with_dependents",
                extra={
                    "recipient": "",
                    "item_count": operators + aircraft,
                    "send_result": "skipped",
                    "reason": "archived_cost_center_with_active_dependents",
                },
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{center.code} is archived but still has {operators} active "
                    f"operator(s) and {aircraft} active aircraft: their expiries "
                    "are not being watched. Reassign them or restore the center."
                )
            )
        for cost_center in cost_centers_to_notify():
            buckets = build_digest(cost_center, today=today)
            item_count = sum(len(items) for items in buckets.values())
            if not item_count:
                continue
            recipient = cost_center.notification_email
            if not recipient:
                skipped += 1
                # Reaching nobody is an operational gap, not a crash: report it
                # and keep going so the other cost centers still get their mail.
                logger.warning(
                    "digest_recipient_missing",
                    extra={
                        "recipient": "",
                        "item_count": item_count,
                        "send_result": "skipped",
                        "reason": "no_responsible_operator_email",
                    },
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"{cost_center.code}: {item_count} expiring items but no "
                        "responsible operator email; skipped."
                    )
                )
                continue

            context = self._context(cost_center, buckets, item_count)
            subject = _("AeroControl · expiry summary for %(center)s") % {
                "center": cost_center.name
            }
            if dry_run:
                self.stdout.write(
                    f"[dry-run] {recipient} <- {cost_center.code}: {item_count} items"
                )
            else:
                message = EmailMultiAlternatives(
                    subject=subject,
                    body=render_to_string("compliance/email/alert_digest.txt", context),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[recipient],
                )
                message.attach_alternative(
                    render_to_string("compliance/email/alert_digest.html", context),
                    "text/html",
                )
                message.send()
            sent += 1
            total_items += item_count
            # Recipient and counts only: the digest body is never logged.
            logger.info(
                "digest_sent",
                extra={
                    "recipient": recipient,
                    "item_count": item_count,
                    "send_result": "dry_run" if dry_run else "sent",
                },
            )
        return sent, skipped, total_items

    @staticmethod
    def _context(cost_center, buckets, item_count):
        groups = []
        for key, _bound in BUCKETS:
            title, color = BUCKET_TITLES[key]
            groups.append(
                {"key": key, "title": title, "color": color, "items": buckets[key]}
            )
        return {
            "cost_center": cost_center,
            "groups": groups,
            "item_count": item_count,
            "base_url": settings.SITE_BASE_URL,
        }
