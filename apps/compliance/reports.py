"""Deterministic compliance KPIs.

Shared by the report views, the `compliance_report` command and the executive
report, so the number a manager reads in a spreadsheet is the same one the
email quotes. No wording or formatting decisions live here.
"""

from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from apps.compliance.digest import HORIZON_DAYS, bucket_for
from apps.compliance.models import Alert, Document
from apps.registry.models import Aircraft, CostCenter, Operator


def documents_for_cost_center(cost_center, queryset=None):
    """Current documents attached to a cost center's aircraft or operators.

    Document points at its subject through a generic foreign key, so the owning
    cost center cannot be reached with a join: the ids are resolved first and
    matched per content type.
    """
    aircraft_ids = list(
        Aircraft.objects.filter(cost_center=cost_center, is_active=True).values_list(
            "pk", flat=True
        )
    )
    operator_ids = list(
        Operator.objects.filter(cost_center=cost_center, is_active=True).values_list(
            "pk", flat=True
        )
    )
    base = queryset if queryset is not None else Document.objects.all()
    if not aircraft_ids and not operator_ids:
        return base.none()
    scope = Q(pk__in=[])
    if aircraft_ids:
        scope |= Q(
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id__in=aircraft_ids,
        )
    if operator_ids:
        scope |= Q(
            content_type=ContentType.objects.get_for_model(Operator),
            object_id__in=operator_ids,
        )
    return base.filter(scope)


def _cost_center_row(cost_center, doc_type, today):
    documents = documents_for_cost_center(
        cost_center,
        Document.objects.filter(is_active=True, is_current_version=True).select_related(
            "doc_type"
        ),
    )
    if doc_type:
        documents = documents.filter(doc_type=doc_type)

    counters = {"expired": 0, "due_7": 0, "due_15": 0, "due_30": 0, "no_expiry": 0}
    total = 0
    for document in documents:
        total += 1
        if document.expiry_date is None:
            # No expiry means permanently valid, not "missing data".
            counters["no_expiry"] += 1
            continue
        bucket = bucket_for(document.expiry_date, today)
        if bucket == "overdue":
            counters["expired"] += 1
        elif bucket is not None:
            counters[bucket] += 1

    valid = total - counters["expired"]
    return {
        "code": cost_center.code,
        "name": cost_center.name,
        "total": total,
        "valid": valid,
        "valid_pct": round(valid * 100 / total, 1) if total else 0.0,
        "expired": counters["expired"],
        "due_7": counters["due_7"],
        "due_15": counters["due_15"],
        "due_30": counters["due_30"],
    }


def _open_alerts(cost_center, today):
    alerts = (
        Alert.objects.filter(is_active=True, is_resolved=False)
        .select_related("alert_rule", "content_type")
        .order_by("triggered_at")
    )
    rows = []
    for alert in alerts:
        rows.append(
            {
                "entity": str(alert.content_object or "—"),
                "entity_type": alert.entity_label,
                "rule": alert.alert_rule.name,
                "triggered_at": alert.triggered_at.date(),
                "age_days": (today - alert.triggered_at.date()).days,
            }
        )
    return rows


def _resolution_stats(start, end):
    """Average alert -> resolution time for alerts resolved in the period."""
    resolved = Alert.objects.filter(
        is_active=True,
        is_resolved=True,
        resolved_at__date__gte=start,
        resolved_at__date__lte=end,
    ).only("triggered_at", "resolved_at")
    days = [
        (alert.resolved_at - alert.triggered_at).total_seconds() / 86400
        for alert in resolved
    ]
    return {
        "resolved_count": len(days),
        "avg_days": round(sum(days) / len(days), 1) if days else None,
    }


def build_compliance_report(start=None, end=None, cost_center=None, doc_type=None):
    """Return the KPI structure for a period.

    `start`/`end` bound the resolution statistics; the expiry counters are
    always relative to today, because "expiring in 7 days" only means anything
    from now.
    """
    today = date.today()
    end = end or today
    start = start or (end - timedelta(days=30))

    centers = CostCenter.objects.filter(is_active=True).order_by("code")
    if cost_center:
        centers = centers.filter(pk=cost_center.pk)

    rows = [_cost_center_row(center, doc_type, today) for center in centers]
    totals = {
        key: sum(row[key] for row in rows)
        for key in ("total", "valid", "expired", "due_7", "due_15", "due_30")
    }
    totals["valid_pct"] = (
        round(totals["valid"] * 100 / totals["total"], 1) if totals["total"] else 0.0
    )

    return {
        "generated_on": today,
        "period": {"start": start, "end": end},
        "horizon_days": HORIZON_DAYS,
        "filters": {
            "cost_center": cost_center.code if cost_center else None,
            "doc_type": doc_type.name if doc_type else None,
        },
        "by_cost_center": rows,
        "totals": totals,
        "open_alerts": _open_alerts(cost_center, today),
        "resolution": _resolution_stats(start, end),
    }


COST_CENTER_HEADERS = [
    "Centro de costo",
    "Nombre",
    "Documentos",
    "Vigentes",
    "% vigentes",
    "Vencidos",
    "Vence <=7d",
    "Vence <=15d",
    "Vence <=30d",
]

ALERT_HEADERS = ["Entidad", "Tipo", "Regla", "Detectada", "Antigüedad (días)"]


def cost_center_rows(report):
    return [
        [
            row["code"],
            row["name"],
            row["total"],
            row["valid"],
            row["valid_pct"],
            row["expired"],
            row["due_7"],
            row["due_15"],
            row["due_30"],
        ]
        for row in report["by_cost_center"]
    ]


def alert_rows(report):
    return [
        [
            alert["entity"],
            alert["entity_type"],
            alert["rule"],
            alert["triggered_at"],
            alert["age_days"],
        ]
        for alert in report["open_alerts"]
    ]
