"""La faena elegida de una pantalla (OPS-8, UX-17), extraída de `dashboard()` (LV-359).

El panel la resolvía en línea; la sección «Cumplimiento» necesita la misma regla. Una sola función
para las dos: «un filtro malformado es un no-op, no un error» (la convención de `SearchMixin`).
"""

from django.core.exceptions import ValidationError

from apps.core.tenancy import scope_queryset_to_tenant
from apps.registry.models import CostCenter


def _lookup(raw, scope_user):
    """La faena activa con esa pk, o `None`: UUID inválido, archivada, inexistente o de otro tenant.

    LV-146: el `try/except` cubre `?cost_center=abc`. Un valor que no es UUID hace que `filter(pk=...)`
    levante `ValidationError` **dentro** de la consulta, y eso no lo atrapa el `.first()`.
    """
    try:
        queryset = CostCenter.objects.filter(pk=raw, is_active=True)
        if scope_user is not None:
            queryset = scope_queryset_to_tenant(queryset, scope_user)
        return queryset.first()
    except (ValueError, ValidationError):
        return None


def resolve_cost_center(request, remember=False, scope_user=None):
    """La faena elegida en `request`, o `None` para «todas».

    - `remember=False`: sólo el `?cost_center=` explícito de la URL; no lee ni escribe la sesión.
    - `remember=True` (el panel, `UX-17`): además se recuerda en la sesión. **La rama se elige por si el
      parámetro *viene*, no por si trae valor**: llegar sin `cost_center` es abrir el panel de nuevo
      (se restaura lo recordado), mientras que `?cost_center=` vacío es pedir «todas» a propósito y
      **borra** el recuerdo. Se guarda la faena que resolvió de verdad y no la cadena cruda, así una
      archivada deja de recordarse sola.
    - `scope_user`: si se pasa, la faena tiene que ser de un tenant que esa persona ve. El panel NO lo
      pasa (hoy no acota por tenant: riesgo anotado en `MASTER_PLAN.md`, LV-359); la sección sí.
    """
    selected = None
    raw = request.GET.get("cost_center")
    if raw:
        selected = _lookup(raw, scope_user)

    if not remember:
        return selected

    if "cost_center" in request.GET:
        if selected is not None:
            request.session["dashboard_cost_center"] = str(selected.pk)
        else:
            request.session.pop("dashboard_cost_center", None)
    else:
        remembered = request.session.get("dashboard_cost_center")
        if remembered:
            selected = _lookup(remembered, scope_user)
            if selected is None:
                request.session.pop("dashboard_cost_center", None)
    return selected
