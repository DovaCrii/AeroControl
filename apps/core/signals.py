def track_status_changes(sender, instance, **kwargs):
    """Create an append-only history row when a tracked status changes."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.status == instance.status:
        return

    from apps.maintenance.models import MaintenanceHistory
    from apps.operations.models import PermissionHistory

    history = {
        "flightpermission": (PermissionHistory, "permission"),
        "maintenancerecord": (MaintenanceHistory, "record"),
    }.get(sender._meta.model_name)
    if history is None:
        return

    history_model, relation = history
    values = {
        relation: instance,
        "previous_status": old.status,
        "new_status": instance.status,
        "changed_by": getattr(instance, "_changed_by", "system"),
    }
    if any(field.name == "notes" for field in history_model._meta.fields):
        values["notes"] = getattr(instance, "_transition_notes", "")
    history_model.objects.create(**values)
