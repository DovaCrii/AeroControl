def track_status_changes(sender, instance, **kwargs):
    """Create an append-only history row when a tracked status changes."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    from apps.geo.models import GeoPlanHistory
    from apps.maintenance.models import MaintenanceHistory
    from apps.operations.models import FlightRequestHistory, PermissionHistory
    from apps.registry.models import InsuranceHistory

    # (history model, its FK back to the record, the field being tracked).
    # The field is part of the mapping because LV-81 tracks a status that is
    # *not* called `status`: an aircraft's own `status` (active/damaged/
    # maintenance) is a different axis that no history table watches, while its
    # insurance filing does advance through a flow and needs the trace.
    history = {
        "flightpermission": (PermissionHistory, "permission", "status"),
        # R9.4: quinto usuario de esta señal. Que agregar el seguimiento de una
        # solicitud SIGO cueste una línea acá es la razón por la que `LV-72`
        # extrajo esto de la vista del permiso.
        "flightrequest": (FlightRequestHistory, "request", "status"),
        "maintenancerecord": (MaintenanceHistory, "record", "status"),
        "geoplan": (GeoPlanHistory, "plan", "status"),
        "aircraft": (InsuranceHistory, "aircraft", "insurance_status"),
    }.get(sender._meta.model_name)
    if history is None:
        return

    history_model, relation, field = history
    previous, new = getattr(old, field), getattr(instance, field)
    if previous == new:
        return
    values = {
        relation: instance,
        "previous_status": previous,
        "new_status": new,
        "changed_by": getattr(instance, "_changed_by", "system"),
        "changed_by_user": getattr(instance, "_changed_by_user", None),
    }
    if any(model_field.name == "notes" for model_field in history_model._meta.fields):
        values["notes"] = getattr(instance, "_transition_notes", "")
    history_model.objects.create(**values)
