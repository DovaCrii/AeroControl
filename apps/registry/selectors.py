"""Shared read selectors for ResourceMovementLog (OPS-1/2/6).

Kept in one place so the Operator/Aircraft/CostCenter timelines and the
standalone movement log list cannot drift apart on how a row's bare
resource_id gets resolved to a human label.
"""

from collections import defaultdict

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import Aircraft, Operator, Qualification, ResourceMovementLog


def label_movements(entries):
    """Attach `.resource_label` to each entry (Operator full_name / Aircraft
    registration), resolved in two queries regardless of how many rows."""
    entries = list(entries)
    operator_ids = [
        entry.resource_id for entry in entries if entry.resource_kind == "operator"
    ]
    aircraft_ids = [
        entry.resource_id for entry in entries if entry.resource_kind == "aircraft"
    ]
    operators = dict(
        Operator.objects.filter(pk__in=operator_ids).values_list("pk", "full_name")
    )
    aircraft = dict(
        Aircraft.objects.filter(pk__in=aircraft_ids).values_list("pk", "registration")
    )
    for entry in entries:
        label = (
            operators.get(entry.resource_id)
            if entry.resource_kind == "operator"
            else aircraft.get(entry.resource_id)
        )
        entry.resource_label = label or str(entry.resource_id)
        # LV-88: the log named the resource in plain text, so reading "RPA-3696
        # moved" and then opening it meant going back to the padrón and
        # searching for it. None when the row points at something that no
        # longer resolves -- the log is append-only and outlives its subject.
        entry.resource_url = (
            reverse(f"{entry.resource_kind}-detail", args=[entry.resource_id])
            if label
            else None
        )
    return entries


def movements_for_resource(resource_kind, resource_id):
    """This resource's own timeline (OPS-6): every movement, newest first."""
    queryset = ResourceMovementLog.objects.filter(
        resource_kind=resource_kind, resource_id=resource_id
    ).select_related("from_cost_center", "to_cost_center", "changed_by_user")
    return label_movements(queryset)


def movements_for_cost_center(cost_center, limit=100):
    """A contract's movement history: anything that moved into or out of it."""
    queryset = ResourceMovementLog.objects.filter(
        Q(from_cost_center=cost_center) | Q(to_cost_center=cost_center)
    ).select_related("changed_by_user", "from_cost_center", "to_cost_center")[:limit]
    return label_movements(queryset)


def operator_aircraft_compatibility_gaps(operators, aircraft_fleet):
    """B4.4: (operator, aircraft) pairs from these rosters where the operator
    holds no current qualification covering that aircraft's model.

    Non-blocking by design (agreed with the user 2026-07-30): a flight
    permission can still be created with a gap, this only flags it. Matched
    against `Aircraft.model` -- `Aircraft.type` is uniformly "RPA" in the real
    fleet and carries no signal to compare against.

    Returns a list of (operator, aircraft) tuples, empty when either roster is
    empty, no qualification type declares `model_keywords`, or every pair is
    covered.
    """
    operators = list(operators)
    aircraft_fleet = list(aircraft_fleet)
    if not operators or not aircraft_fleet:
        return []

    today = timezone.localdate()
    current_qualifications = (
        Qualification.objects.filter(operator__in=operators, is_active=True)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
        .select_related("qualification_type")
    )
    keywords_by_operator = defaultdict(list)
    for qualification in current_qualifications:
        keywords_by_operator[qualification.operator_id].extend(
            qualification.qualification_type.keyword_list()
        )

    gaps = []
    for operator in operators:
        keywords = keywords_by_operator.get(operator.pk, [])
        for aircraft in aircraft_fleet:
            model = (aircraft.model or "").lower()
            if not any(keyword in model for keyword in keywords):
                gaps.append((operator, aircraft))
    return gaps
