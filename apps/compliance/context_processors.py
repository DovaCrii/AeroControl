from apps.core.tenancy import scope_queryset_to_visible_tenants

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
    # LV-372 (F-08): el número de la barra lateral también es dato de alertas, y contaba las de
    # **todas** las empresas. Subconsulta y no lista resuelta: esto corre en cada página y muchas
    # pantallas tienen techo de consultas.
    return {
        "unresolved_alert_count": scope_queryset_to_visible_tenants(
            Alert.objects.filter(is_active=True, is_resolved=False),
            request.user,
            "alert_rule__tenant_id",
        ).count()
    }
