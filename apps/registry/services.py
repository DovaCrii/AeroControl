"""Write services for the registry: operations that change assignments.

Kept apart from selectors.py (which is read-only) so the one place that moves
resources between cost centers in bulk stays easy to find and test.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AircraftAssignment, OperatorAssignment


def _bulk_assign(
    *,
    model,
    resource_field,
    resources,
    cost_center,
    status,
    purpose,
    purpose_detail,
    user,
):
    """Shared by bulk_assign_operators and bulk_assign_aircraft (R5.6) --
    OperatorAssignment/AircraftAssignment both extend the same abstract
    ResourceAssignment (resource_field), so the move logic itself does not
    differ. See bulk_assign_operators for the reasoning (LV-18)."""
    today = timezone.localdate()
    moved = 0
    for resource in resources:
        current = model.objects.filter(
            **{resource_field: resource},
            is_active=True,
            status__in=model.ACTIVE_STATUSES,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        if current.filter(cost_center=cost_center).exists():
            continue  # already here
        # Close any open assignment elsewhere before opening the new one, so the
        # signal sees a single active assignment and logs one clean "reassigned".
        current.exclude(cost_center=cost_center).update(status="ended", end_date=today)
        assignment = model(
            cost_center=cost_center,
            start_date=today,
            status=status,
            purpose=purpose,
            purpose_detail=purpose_detail,
            **{resource_field: resource},
        )
        assignment._changed_by_user = user
        assignment.save()
        moved += 1
    return moved


@transaction.atomic
def bulk_assign_operators(
    *, operators, cost_center, status, purpose, purpose_detail, user
):
    """Assign several operators to one cost center in a single action (LV-18).

    An operator belongs to a single cost center, so one already active on a
    *different* cost center is moved: its open assignment is ended today and a
    fresh one is opened on the target. Ending the old row first means the new
    one never trips the per-operator overlap guard, so 5 or 10 operators can be
    reassigned at once instead of one by one. An operator already on the target
    is left untouched (no churn, no duplicate movement-log entry).

    The new assignment is saved (not bulk-created) so the post_save signal keeps
    ``Operator.cost_center`` and the ``ResourceMovementLog`` in sync; each move
    is attributed to ``user``. Returns the number of operators actually moved.
    """
    return _bulk_assign(
        model=OperatorAssignment,
        resource_field="operator",
        resources=operators,
        cost_center=cost_center,
        status=status,
        purpose=purpose,
        purpose_detail=purpose_detail,
        user=user,
    )


@transaction.atomic
def bulk_assign_aircraft(
    *, aircraft, cost_center, status, purpose, purpose_detail, user
):
    """R5.6: the same bulk-move pattern as bulk_assign_operators (LV-18), for
    aircraft -- OperatorBulkAssign existed, AircraftAssignment had no
    equivalent and still required moving aircraft one at a time."""
    return _bulk_assign(
        model=AircraftAssignment,
        resource_field="aircraft",
        resources=aircraft,
        cost_center=cost_center,
        status=status,
        purpose=purpose,
        purpose_detail=purpose_detail,
        user=user,
    )
