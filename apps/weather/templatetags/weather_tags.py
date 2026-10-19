"""Etiquetas de plantilla del tiempo (LV-347)."""

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag(takes_context=True)
def weather_card_enabled(context):
    """¿Se dibuja el hueco de la tarjeta del tiempo? Apagada por `WEATHER_ENABLED` y sin permiso, no.

    Con esto apagado el panel ni siquiera pide el fragmento: no hay petición ni hueco.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    return bool(
        getattr(settings, "WEATHER_ENABLED", False)
        and user is not None
        and user.has_perm("weather.view_userweatherlocation")
    )
