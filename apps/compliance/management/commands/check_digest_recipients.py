"""Report which cost centers can actually receive the expiry digest.

`send_alert_digest` only looks at cost centers that already have expiring items,
so a center with no documents loaded yet is never checked -- and a missing
recipient stays invisible until the first expiry, when the mail silently goes
nowhere. This lists *every* active cost center and whether it has a reachable
digest recipient, so the gaps can be fixed up front. Read-only.

Fix a gap in the cost center's Edit form (Responsible operator, or the External
contact fields) or via the Django admin. See docs/compliance-setup.md, "Paso 1".
"""

from django.core.management.base import BaseCommand

from apps.compliance.digest import cost_centers_to_notify


def recipient_status(cost_center):
    """Return (reachable, email, explanation) mirroring `notification_email`."""
    operator = cost_center.responsible_operator
    email = cost_center.notification_email
    if email:
        if operator and operator.is_active and operator.email == email:
            return True, email, f"operator: {operator.full_name}"
        return True, email, "external contact"
    # No reachable recipient -- say why so it is actionable.
    if operator and not operator.is_active:
        return False, "", "responsible operator is archived; set another or a contact"
    if operator and not operator.email:
        return False, "", "responsible operator has no email; add one or set a contact"
    return False, "", "no responsible operator or external contact set"


class Command(BaseCommand):
    help = "Report which active cost centers have a reachable expiry-digest recipient."

    def handle(self, *args, **options):
        centers = list(cost_centers_to_notify())
        reachable = 0
        self.stdout.write(
            f"Digest recipient readiness ({len(centers)} cost centers):\n"
        )
        for center in centers:
            ok, email, explanation = recipient_status(center)
            reachable += int(ok)
            label = f"{center.code} {center.name or ''}".strip()
            if ok:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK       {label:32} {email}  ({explanation})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  MISSING  {label:32} {explanation}")
                )
        missing = len(centers) - reachable
        summary = f"\n{reachable} reachable, {missing} missing a recipient."
        self.stdout.write(
            self.style.SUCCESS(summary) if not missing else self.style.WARNING(summary)
        )
        if missing:
            self.stdout.write(
                "Fix each in the cost center's Edit form (Responsible operator or "
                "External contact), or via /admin."
            )
