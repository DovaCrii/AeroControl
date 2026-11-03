"""Shared logic for the monthly compliance review (LV-30).

The end-of-month question is simple: for every cost center that flew this month,
are its operational records (flight logs, checklists, inspections) on file? Both
`check_monthly_records` (which creates the reviews and mails the reviewer) and
the monthly-review page compute the same flights-vs-records counts, so that
lives here once.
"""

import calendar
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType


def month_start(day):
    """First day of the month `day` falls in."""
    return day.replace(day=1)


def month_bounds(period):
    """(first_day, last_day) of the month `period` belongs to."""
    first = month_start(period)
    last = date(
        first.year, first.month, calendar.monthrange(first.year, first.month)[1]
    )
    return first, last


def is_last_day_of_month(day):
    """True when tomorrow is a different month -- the day the month closes."""
    _first, last = month_bounds(day)
    return day == last


def previous_month_start(day):
    """First day of the month before `day`'s month."""
    return month_start(month_start(day) - timedelta(days=1))


def is_review_deadline_day(day):
    """R6.5: the internal procedure's deadline for Dirección to have signed
    off last month's compliance review -- the 15th of the following month."""
    return day.day == 15


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


def monthly_close_rows(period, cost_centers, doc_types):
    """LV-262: el cierre del mes, una fila por faena — vuelos, registros por tipo y
    la revisión, si la hay.

    Pedido del usuario el 2026-09-25: unificar «Registros operacionales» y
    «Cumplimiento mensual» en una herramienta más condensada, pensando en la
    etapa de carga de datos. Eran dos mitades de la misma pregunta: una mostraba
    los papeles y la otra preguntaba si estaban.

    ⚠️ **Se listan todas las faenas que operan, no sólo las que volaron en la
    app.** La revisión de `LV-30` sólo nace para una faena con vuelos registrados
    (`cost_centers_that_flew`), y en producción había **cero** vuelos registrados
    el 2026-09-25 — la bitácora digital todavía no se usa, las bitácoras llegan
    en PDF. Con el criterio viejo esta pantalla habría quedado vacía para
    siempre, justo cuando empiezan a cargarse los registros. El número de vuelos
    se muestra como dato; no decide si la fila existe.

    Tres consultas en total, no tres por faena: el cierre se abre una vez al mes,
    pero con quince faenas y un bucle por fila serían cuarenta y cinco.
    """
    from django.db.models import Count

    from apps.operations.models import FlightRecord
    from apps.registry.models import CostCenter

    from .models import Document, MonthlyComplianceReview

    first, last = month_bounds(period)
    ids = [centre.pk for centre in cost_centers]
    flights = dict(
        FlightRecord.objects.filter(
            is_active=True,
            aircraft__cost_center_id__in=ids,
            actual_date__gte=first,
            actual_date__lte=last,
        )
        .values_list("aircraft__cost_center_id")
        .annotate(total=Count("pk"))
    )
    records = {}
    for object_id, doc_type_id, total in (
        Document.objects.filter(
            is_active=True,
            is_current_version=True,
            doc_type__is_operational_record=True,
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id__in=ids,
            issue_date__gte=first,
            issue_date__lte=last,
        )
        .values_list("object_id", "doc_type_id")
        .annotate(total=Count("pk"))
    ):
        records.setdefault(str(object_id), {})[doc_type_id] = total
    reviews = {
        review.cost_center_id: review
        for review in MonthlyComplianceReview.objects.filter(
            is_active=True, cost_center_id__in=ids, period=first
        ).select_related("reviewed_by")
    }

    rows = []
    for centre in cost_centers:
        by_type = records.get(str(centre.pk), {})
        rows.append(
            {
                "cost_center": centre,
                "flights": flights.get(centre.pk, 0),
                "records": [
                    {"doc_type": doc_type, "count": by_type.get(doc_type.pk, 0)}
                    for doc_type in doc_types
                ],
                "records_total": sum(by_type.values()),
                "missing_types": [
                    doc_type for doc_type in doc_types if not by_type.get(doc_type.pk)
                ],
                "review": reviews.get(centre.pk),
            }
        )
    return rows


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
    return CostCenter.objects.filter(pk__in=list(cc_ids), is_active=True).order_by(
        "code"
    )
