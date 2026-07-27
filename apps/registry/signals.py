"""Keep the resource→cost-center denormalization in sync, and log every move.

`Operator.cost_center` / `Aircraft.cost_center` are the field the calendar,
digests and reports read. From OPS-1 they are a *derived* value: whenever a
resource's assignments change, this recomputes the current cost center and,
when it actually changed, appends a ResourceMovementLog row. The signal is the
single writer of that field.
"""

from django.db.models import Q
from django.utils import timezone

from .models import (
    AircraftAssignment,
    OperatorAssignment,
    ResourceMovementLog,
)


def _current_cost_center(model, resource_field, resource_id):
    """The cost center a resource currently belongs to, or None.

    Current = an active, non-archived assignment whose period includes today
    (open-ended assignments count); the most recently started one wins.
    """
    today = timezone.localdate()
    assignment = (
        model.objects.filter(
            is_active=True,
            status__in=model.ACTIVE_STATUSES,
            **{f"{resource_field}_id": resource_id},
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .order_by("-start_date")
        .first()
    )
    return assignment.cost_center if assignment else None


def _sync(model, resource_field, kind, instance):
    resource = getattr(instance, resource_field)
    new_cc = _current_cost_center(model, resource_field, resource.pk)
    old_cc_id = resource.cost_center_id
    new_cc_id = new_cc.pk if new_cc else None
    if old_cc_id == new_cc_id:
        return
    if new_cc_id is None:
        movement = "released"
    elif old_cc_id is None:
        movement = "assigned"
    else:
        movement = "reassigned"
    ResourceMovementLog.objects.create(
        resource_kind=kind,
        resource_id=resource.pk,
        movement=movement,
        from_cost_center_id=old_cc_id,
        to_cost_center=new_cc,
        # The view sets these on the assignment instance when it has a request.
        changed_by_user=getattr(instance, "_changed_by_user", None),
        detail=getattr(instance, "_movement_detail", ""),
    )
    resource.cost_center = new_cc
    resource.save(update_fields=["cost_center", "updated_at"])


def sync_operator_assignment(sender, instance, **kwargs):
    _sync(OperatorAssignment, "operator", "operator", instance)


def sync_aircraft_assignment(sender, instance, **kwargs):
    _sync(AircraftAssignment, "aircraft", "aircraft", instance)


def track_aircraft_location(sender, instance, **kwargs):
    """OPS-3: log a move whenever Aircraft.current_location/current_site changes.

    pre_save (not post_save): needs the *previous* row to compare against, the
    same shape as apps/core/signals.py's track_status_changes, but writing to
    the generic ResourceMovementLog instead of a per-model history table --
    location isn't a workflow status, and the log already models "resource
    moved" independently of cost-center assignment.
    """
    if not instance.pk:
        return  # first save: nothing to compare against, no transition to log
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if (
        old.current_location == instance.current_location
        and old.current_site_id == instance.current_site_id
    ):
        return
    ResourceMovementLog.objects.create(
        resource_kind="aircraft",
        resource_id=instance.pk,
        movement="location_changed",
        from_cost_center_id=old.current_site_id
        if old.current_location == "on_site"
        else None,
        to_cost_center_id=(
            instance.current_site_id if instance.current_location == "on_site" else None
        ),
        detail=f"{old.get_current_location_display()} → {instance.get_current_location_display()}",
        changed_by_user=getattr(instance, "_changed_by_user", None),
    )
