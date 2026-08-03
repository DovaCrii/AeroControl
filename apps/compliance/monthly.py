"""Shared logic for the monthly compliance review (LV-30).

The end-of-month question is simple: for every cost center that flew this month,
are its operational records (flight logs, checklists, inspections) on file? Both
`check_monthly_records` (which creates the reviews and mails the reviewer) and
the monthly-review page compute the same flights-vs-records counts, so that
lives here once.
"""

import calendar
from datetime import date

from django.contrib.contenttypes.models import ContentType


def month_start(day):
    """First day of the month `day` falls in."""
    return day.replace(day=1)


def month_bounds(period):
    """(first_day, last_day) of the month `period` belongs to."""
    first = month_start(period)
    last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    return first, last


def is_last_day_of_month(day):
    """True when tomorrow is a different month -- the day the month closes."""
    _first, last = month_bounds(day)
    return day == last


def flights_in_month(cost_center, period):
    """Count of flight records this cost center flew in `period`'s month."""
    from apps.operations.models import FlightRecord

    first, last = month_bounds(period)
    return FlightRecord.objects.filter(
        is_active=True,
        aircraft__cost_center=cost_center,
        actual_date__gte=first,
        actual_date__lte=last,
    ).count()


def operational_records_qs(cost_center, period):
    """Operational-record documents filed for this cost center in `period`."""
    from apps.registry.models import CostCenter

    from .models import Document

    first, last = month_bounds(period)
    cc_ct = ContentType.objects.get_for_model(CostCenter)
    return Document.objects.filter(
        is_active=True,
        is_current_version=True,
        doc_type__is_operational_record=True,
        content_type=cc_ct,
        object_id=cost_center.pk,
        issue_date__gte=first,
        issue_date__lte=last,
    )


def records_in_month(cost_center, period):
    """Count of operational-record documents filed for `cost_center` in the month."""
    return operational_records_qs(cost_center, period).count()


def cost_centers_that_flew(period):
    """Active cost centers with at least one flight in `period`'s month.

    These are the cost centers a monthly review is created for: one with no
    flights has no operational records to be missing.
    """
    from apps.operations.models import FlightRecord
    from apps.registry.models import CostCenter

    first, last = month_bounds(period)
    cc_ids = (
        FlightRecord.objects.filter(
            is_active=True,
            actual_date__gte=first,
            actual_date__lte=last,
            aircraft__cost_center__isnull=False,
        )
        .values_list("aircraft__cost_center_id", flat=True)
        .distinct()
    )
    return CostCenter.objects.filter(pk__in=list(cc_ids), is_active=True).order_by("code")
