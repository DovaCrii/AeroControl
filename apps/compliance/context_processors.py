from .models import Alert


def unresolved_alert_count(request):
    if not request.user.is_authenticated:
        return {"unresolved_alert_count": 0}
    return {
        "unresolved_alert_count": Alert.objects.filter(
            is_active=True, is_resolved=False
        ).count()
    }
