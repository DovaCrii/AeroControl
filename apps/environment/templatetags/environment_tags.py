from django import template

from apps.environment.strip import cells_for
from apps.environment.tabs import tabs_for

register = template.Library()


@register.simple_tag(takes_context=True)
def environment_entry(context):
    """La URL del ítem único «Entorno» del menú, o `""` si la persona no puede abrir ninguna pestaña."""
    request = context.get("request")
    user = getattr(request, "user", None)
    tabs = tabs_for(user) if user is not None else []
    return tabs[0]["url"] if tabs else ""


@register.simple_tag(takes_context=True)
def environment_strip_enabled(context):
    """¿Se dibuja el hueco de la franja «Entorno hoy» del panel? (LV-358, E2).

    Sólo si hay al menos una celda: la persona tiene el permiso de su fuente y su interruptor está
    encendido. Sin ninguna no hay franja, ni petición, ni hueco (y el panel no carga el script).
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    return user is not None and bool(cells_for(user))
