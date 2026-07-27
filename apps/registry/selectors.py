"""Shared read selectors for ResourceMovementLog (OPS-1/2/6).

Kept in one place so the Operator/Aircraft/CostCenter timelines and the
standalone movement log list cannot drift apart on how a row's bare
resource_id gets resolved to a human label.
"""

from django.db.models import Q

from .models import Aircraft, Operator, ResourceMovementLog


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
