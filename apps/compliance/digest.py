"""Expiry digest assembly.

Kept out of the management command so Bloque 6 (executive reports) can reuse
the same buckets instead of recomputing them, and so it is testable without
invoking mail.
"""

from datetime import timedelta

from django.utils import timezone

from apps.compliance.models import Document
from apps.registry.models import CostCenter, Operator, Qualification

# Ordered most urgent first; the last bound is the digest horizon.
BUCKETS = [
    ("overdue", None),
    ("due_7", 7),
    ("due_15", 15),
    ("due_30", 30),
]
HORIZON_DAYS = 30


def bucket_for(expiry, today):
    """Return the urgency bucket key for an expiry date."""
    if expiry < today:
        return "overdue"
    days_left = (expiry - today).days
    if days_left <= 7:
        return "due_7"
    if days_left <= 15:
        return "due_15"
    if days_left <= HORIZON_DAYS:
        return "due_30"
    return None


def _documents_for(cost_center, cutoff):
    """Expiring current documents attached to this cost center."""
    from apps.compliance.reports import documents_for_cost_center

    return documents_for_cost_center(
        cost_center,
        Document.objects.filter(
            is_active=True,
            is_current_version=True,
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
        ).select_related("doc_type"),
    ).order_by("expiry_date")


def build_digest(cost_center, today=None):
    """Return {bucket: [item, ...]} of expiring items for a cost center.

    Items are dicts with kind/label/detail/expiry_date/url_path so the email
    templates stay free of model knowledge.
    """
    today = today or timezone.localdate()
    cutoff = today + timedelta(days=HORIZON_DAYS)
    operator_ids = list(
        Operator.objects.filter(cost_center=cost_center, is_active=True).values_list(
            "pk", flat=True
        )
    )

    buckets = {key: [] for key, _bound in BUCKETS}

    qualifications = (
        Qualification.objects.filter(
            operator_id__in=operator_ids,
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
        )
        .select_related("operator")
        .order_by("expiry_date")
    )
    for qualification in qualifications:
        key = bucket_for(qualification.expiry_date, today)
        if key:
            buckets[key].append(
                {
                    "kind": "qualification",
                    "label": qualification.qualification_type,
                    "detail": str(qualification.operator),
                    "expiry_date": qualification.expiry_date,
                    "url_path": f"/registry/qualification/{qualification.pk}/",
                }
            )

    for document in _documents_for(cost_center, cutoff):
        key = bucket_for(document.expiry_date, today)
        if key:
            buckets[key].append(
                {
                    "kind": "document",
                    "label": document.title,
                    "detail": str(document.doc_type),
                    "expiry_date": document.expiry_date,
                    "url_path": f"/compliance/document/{document.pk}/",
                }
            )

    for items in buckets.values():
        items.sort(key=lambda item: item["expiry_date"])
    return buckets


def digest_item_count(buckets):
    return sum(len(items) for items in buckets.values())


def cost_centers_to_notify():
    """Active cost centers, most specific first, for the digest run."""
    return (
        CostCenter.objects.filter(is_active=True)
        .select_related("responsible_operator")
        .order_by("code")
    )


def archived_centers_with_active_dependents():
    """Archived cost centers whose operators or aircraft are still active.

    Archiving a center drops it from the digest and the report silently -- the
    exact compliance blind spot the digest exists to prevent. The command
    reports these instead of staying quiet. Returns (center, operators,
    aircraft) tuples.
    """
    from django.db.models import Count, Q

    centers = (
        CostCenter.objects.filter(is_active=False)
        .annotate(
            active_operators=Count(
                "operators", filter=Q(operators__is_active=True), distinct=True
            ),
            active_aircraft=Count(
                "aircraft", filter=Q(aircraft__is_active=True), distinct=True
            ),
        )
        .filter(Q(active_operators__gt=0) | Q(active_aircraft__gt=0))
        .order_by("code")
    )
    return [
        (center, center.active_operators, center.active_aircraft) for center in centers
    ]
