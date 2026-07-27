"""OPS-7: log every change to GeoPlan.flight_permission."""

from .models import GeoPlanPermissionLink


def track_flight_permission_link(sender, instance, **kwargs):
    if not instance.pk:
        return  # first save: nothing to compare against, no change to log
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.flight_permission_id == instance.flight_permission_id:
        return
    GeoPlanPermissionLink.objects.create(
        plan=instance,
        previous_permission_id=old.flight_permission_id,
        new_permission_id=instance.flight_permission_id,
        changed_by_user=getattr(instance, "_changed_by_user", None),
    )
