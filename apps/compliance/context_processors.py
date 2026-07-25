from .models import Alert


def unresolved_alert_count(request):
    """Alert count for the sidebar badge, or None without the permission.

    None (not 0): the template hides the badge entirely, because an aggregate
    over alerts is still alert data — the same read contract the calendar
    enforces per event source.
    """
    if not request.user.is_authenticated or not request.user.has_perm(
        "compliance.view_alert"
    ):
        return {"unresolved_alert_count": None}
    return {
        "unresolved_alert_count": Alert.objects.filter(
            is_active=True, is_resolved=False
        ).count()
    }
