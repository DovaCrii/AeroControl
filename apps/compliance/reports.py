"""Deterministic compliance KPIs.

Shared by the report views, the `compliance_report` command and the executive
report, so the number a manager reads in a spreadsheet is the same one the
email quotes. No wording or formatting decisions live here.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone

from apps.compliance.digest import HORIZON_DAYS
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
        Document.objects.filter(is_active=True, is_current_version=True),
    )
    if doc_type:
        documents = documents.filter(doc_type=doc_type)

    # One aggregate instead of iterating every document in Python: the loop
    # loaded the cost center's whole document table per row, which turns the
    # report from instant to seconds within a few years of accumulation.
    boundaries = {
        "due_7": today + timedelta(days=7),
        "due_15": today + timedelta(days=15),
        "due_30": today + timedelta(days=30),
    }
    counted = documents.aggregate(
        total=Count("pk"),
        expired=Count("pk", filter=Q(expiry_date__lt=today)),
        due_7=Count(
            "pk", filter=Q(expiry_date__gte=today, expiry_date__lte=boundaries["due_7"])
        ),
        due_15=Count(
            "pk",
            filter=Q(
                expiry_date__gt=boundaries["due_7"],
                expiry_date__lte=boundaries["due_15"],
            ),
        ),
        due_30=Count(
            "pk",
            filter=Q(
                expiry_date__gt=boundaries["due_15"],
                expiry_date__lte=boundaries["due_30"],
            ),
        ),
    )
    counters = {key: counted[key] for key in ("expired", "due_7", "due_15", "due_30")}
    total = counted["total"]

    # LV-49: DGAC vigencias (Operator.credential_expiry, Aircraft.insurance_expiry)
    # already drive real alerts (LV-29's "Credenciales DGAC"/"Seguros JAC" rules)
    # but were never reflected here, so this report read 0/0.0% for every cost
    # center while the alert list showed real open items for the same data.
    # Only merged in when no doc_type filter narrows the view: vigencias are
    # not Document rows and have no doc_type, so a type-filtered report should
    # not silently pull them back in.
    if doc_type is None:
        for model, field in (
            (Operator, "credential_expiry"),
            (Aircraft, "insurance_expiry"),
        ):
            vigencias = _vigencia_bucket_counts(
                model.objects.filter(cost_center=cost_center, is_active=True),
                field,
                today,
                boundaries,
            )
            total += vigencias["total"]
            for key in ("expired", "due_7", "due_15", "due_30"):
                counters[key] += vigencias[key]

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


def _vigencia_bucket_counts(queryset, date_field, today, boundaries):
    """Expired/due-soon counters for a DGAC vigencia field.

    Unlike Document.expiry_date -- where null means "this document type never
    expires" and the row still counts as valid -- a null vigencia means the
    value was never entered in the fiche. Those rows are excluded entirely
    rather than counted as valid, matching how generate_alerts already treats
    these same fields (LV-29: only aircraft/operators with a value set are
    watched).
    """
    present = queryset.filter(**{f"{date_field}__isnull": False})
    return present.aggregate(
        total=Count("pk"),
        expired=Count("pk", filter=Q(**{f"{date_field}__lt": today})),
        due_7=Count(
            "pk",
            filter=Q(
                **{f"{date_field}__gte": today, f"{date_field}__lte": boundaries["due_7"]}
            ),
        ),
        due_15=Count(
            "pk",
            filter=Q(
                **{
                    f"{date_field}__gt": boundaries["due_7"],
                    f"{date_field}__lte": boundaries["due_15"],
                }
            ),
        ),
        due_30=Count(
            "pk",
            filter=Q(
                **{
                    f"{date_field}__gt": boundaries["due_15"],
                    f"{date_field}__lte": boundaries["due_30"],
                }
            ),
        ),
    )


# Oldest-first cap on the open-alert list. The report is a status overview,
# not the alert queue: past this size the marginal row adds nothing the
# alert list page does not show better.
OPEN_ALERTS_LIMIT = 200


def _open_alerts(cost_center, today):
    alerts = list(
        Alert.objects.filter(is_active=True, is_resolved=False)
        .select_related("alert_rule", "content_type")
        .order_by("triggered_at")[:OPEN_ALERTS_LIMIT]
    )
    # str(alert.content_object) resolved each watched entity with its own
    # query - one per open alert, unbounded. Fetch them grouped by type
    # instead: one query per distinct content type.
    by_type = {}
    for alert in alerts:
        by_type.setdefault(alert.content_type, set()).add(alert.object_id)
    entities = {}
    for content_type, ids in by_type.items():
        model = content_type.model_class()
        if model is None:
            continue
        for obj in model._default_manager.filter(pk__in=ids):
            entities[(content_type.pk, obj.pk)] = obj

    rows = []
    for alert in alerts:
        entity = entities.get((alert.content_type_id, alert.object_id))
        # The received cost_center filter used to be accepted and ignored, so
        # a filtered report still listed every cost center's alerts.
        if cost_center is not None and entity is not None:
            entity_center = getattr(entity, "cost_center_id", None)
            if entity_center is None:
                operator = getattr(entity, "operator", None)
                entity_center = getattr(operator, "cost_center_id", None)
            if entity_center is not None and entity_center != cost_center.pk:
                continue
        rows.append(
            {
                "entity": str(entity or "—"),
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
    # `timezone.localdate()`, not `date.today()`: `_resolution_stats` filters
    # `resolved_at__date`, which the database evaluates in the project timezone.
    # A naive OS date disagrees with it whenever the two differ — with
    # TIME_ZONE="UTC" and an operator west of Greenwich, that is every evening,
    # and alerts resolved in those hours dropped out of the period silently.
    today = timezone.localdate()
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
        # LV-8f: maintenance still needing planning is an open compliance gap.
        "incomplete_maintenance": _incomplete_maintenance_count(cost_center),
    }


def _incomplete_maintenance_count(cost_center):
    """LV-8e/8f: maintenance flagged 'to be defined' or missing a scheduled
    date, and not yet completed. A cross-app read, scoped by cost center via
    the aircraft when one is selected."""
    from apps.maintenance.models import MaintenanceRecord

    queryset = MaintenanceRecord.objects.filter(
        is_active=True, status__in=["pending", "in_progress"]
    ).filter(Q(maintenance_type="to_be_defined") | Q(scheduled_date__isnull=True))
    if cost_center is not None:
        queryset = queryset.filter(aircraft__cost_center=cost_center)
    return queryset.count()


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
