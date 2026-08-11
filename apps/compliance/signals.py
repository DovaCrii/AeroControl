"""LV-71: renewing a watched date closes its own alert, with a reason.

The asymmetry this fixes: four paths already closed an alert automatically
(a document superseded by a new version, a maintenance completed, a monthly
review signed, a Kanban card completed) but **renewing the thing the alert is
about did not**. Updating `Aircraft.insurance_expiry`, `credential_expiry`, a
qualification or a permit's `valid_until` left its alert open, so the operator
had to renew the policy *and* then resolve the alert by hand -- and those are
most of the real alerts in production.

Why it closes with a reason instead of silently: `Alert.resolve()` accepts an
optional reason precisely because the automatic callers have no human to ask
(R6.2), but a resolution with no reason is weak evidence for ISO 10.2, which
asks for the root cause on record. Deciding between "uniform behaviour" and
"keep the evidence" was the tension LV-71 recorded; the user chose to keep both
by writing a traceable machine reason: *"Vigencia renovada al AAAA-MM-DD
(cierre automático)"*. Nobody has to type it and an auditor can still see why
the alert closed.

`post_save`, not `pre_save` -- the R6.1 lesson: `Alert.resolve()` re-saves the
linked Kanban task, and at `pre_save` that inner write races the outer save that
has not landed yet and loses.

Only date fields. A rule watching `status` (open maintenance, pending monthly
review) already has its own closing path, and "status moved" does not mean
"no longer a concern" the way a date moving out of the window does.

Known limitation, deliberate: `queryset.update()` does not fire signals, so a
bulk date change (a data migration, a management command) will not close alerts.
That is the same trade-off every other signal in this project already makes, and
`generate_alerts` self-heals the opposite direction anyway.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _


def resolve_alerts_when_watched_date_is_renewed(sender, instance, **kwargs):
    from .models import Alert

    content_type = ContentType.objects.get_for_model(sender)
    open_alerts = Alert.objects.filter(
        content_type=content_type,
        object_id=instance.pk,
        is_resolved=False,
        is_active=True,
    ).select_related("alert_rule")

    today = timezone.localdate()
    for alert in open_alerts:
        field_name = alert.alert_rule.field_to_watch
        try:
            field = sender._meta.get_field(field_name)
        except FieldDoesNotExist:
            # A rule pointing at a field this model no longer has: not this
            # signal's problem to report -- generate_alerts already warns about
            # invalid rules on every run. Caught narrowly (not `except
            # Exception`, which bandit B112 rightly flags) so a real error here
            # still surfaces instead of being swallowed by a `continue`.
            continue
        if not isinstance(field, models.DateField):
            continue
        value = getattr(instance, field_name, None)
        if value is None:
            # Cleared, not renewed. Leaving the alert open is the safe reading:
            # a missing vigencia is a worse state than an expiring one.
            continue
        if hasattr(value, "date"):  # DateTimeField
            value = value.date()
        # The same window generate_alerts uses to decide an alert is due, so the
        # two cannot disagree: closing an alert that the next 06:00 run would
        # immediately recreate would just make it flap.
        if value <= today + timedelta(days=alert.alert_rule.days_before_expiry):
            continue
        # msgid in English, Spanish in the catalog: the project keeps source
        # strings in English and `test_source_strings_are_written_in_english`
        # fails on an accent in a source literal (it caught this one).
        alert.resolve(
            reason=_("Validity renewed to %(date)s (automatic closure)")
            % {"date": value.isoformat()}
        )
