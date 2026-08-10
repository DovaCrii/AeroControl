"""R5.1: bumps MaintenanceRecord.status_changed_at on every real status
change, and drives Aircraft.current_location/status at the two edges of the
workshop chain -- entering it when a record is sent out ("sent"), leaving it
when one arrives back and is marked done (arriving at "completed" *from*
"in_transit" -- completing the short in-house path, from "in_progress", never
touches the aircraft, matching its behaviour before this workflow existed).

The states in between (at_workshop/finished/in_transit) do not change where
the aircraft physically is relative to what already happened when it left,
so only the two edges act. Reuses Aircraft.current_location's own
track_aircraft_location signal (apps/registry/signals.py) for the
ResourceMovementLog entry -- this only sets the fields, it does not write
history itself.
"""

from django.utils import timezone

from .models import MaintenanceRecord


def sync_maintenance_status_transition(sender, instance, **kwargs):
    try:
        old_status = MaintenanceRecord.objects.values_list("status", flat=True).get(
            pk=instance.pk
        )
    except MaintenanceRecord.DoesNotExist:
        instance.status_changed_at = timezone.now()
        return
    if old_status == instance.status:
        return
    instance.status_changed_at = timezone.now()

    aircraft = instance.aircraft
    if instance.status == "sent":
        aircraft.current_location = "maintenance"
        aircraft.current_site = None
        aircraft.status = "maintenance"
    elif instance.status == "completed" and old_status == "in_transit":
        aircraft.current_location = "headquarters"
        aircraft.status = "active"
    else:
        return
    # The view sets this on the record when it has a request (same idiom as
    # apps/registry/signals.py's ResourceMovementLog attribution).
    aircraft._changed_by_user = getattr(instance, "_changed_by_user", None)
    aircraft.save(
        update_fields=["current_location", "current_site", "status", "updated_at"]
    )
