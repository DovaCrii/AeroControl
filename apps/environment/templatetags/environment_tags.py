from django import template

from apps.environment.tabs import tabs_for

register = template.Library()


@register.simple_tag(takes_context=True)
def environment_entry(context):
    """La URL del ítem único «Entorno» del menú, o `""` si la persona no puede abrir ninguna pestaña."""
    request = context.get("request")
    user = getattr(request, "user", None)
    tabs = tabs_for(user) if user is not None else []
    return tabs[0]["url"] if tabs else ""
