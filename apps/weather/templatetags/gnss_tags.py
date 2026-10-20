"""Etiquetas de plantilla de la tarjeta «Centelleo GNSS» (LV-352, fase 2).

La tarjeta es SOLO informativa: una referencia estadística tomada de GEOCOM (portal
`centelleo.geocom.cl`, operado con el área de desarrollo de Trimble). No llama a nadie, no lee
datos en vivo y no se cruza con permisos, faenas ni aeronaves. La ventana se calcula en
`apps/weather/gnss.py`; aquí sólo se arma lo que dibuja la plantilla. Se apaga con
`GNSS_SCINTILLATION_ENABLED=False`.
"""

from django import template
from django.conf import settings
from django.utils import timezone

from apps.weather import gnss

register = template.Library()


@register.simple_tag
def gnss_card_enabled():
    """¿Se dibuja la tarjeta? Sólo depende del interruptor (encendido por omisión)."""
    return bool(getattr(settings, "GNSS_SCINTILLATION_ENABLED", True))


def build_gnss_card(now=None):
    """Todo lo que dibuja la tarjeta, calculado aquí y no en la plantilla."""
    params = gnss.params_from_settings()
    state = gnss.window_state(now or timezone.now(), params)
    if state["active"]:
        status = "on"
    elif state["next_start"] is not None:
        status = "off"
    else:
        status = "outside"
    return {
        "enabled": gnss_card_enabled(),
        "status": status,
        "symbol": "▲" if status == "on" else "●",
        "until": timezone.localtime(state["next_end"]) if status == "on" else None,
        "next_start": timezone.localtime(state["next_start"])
        if status == "off"
        else None,
        "night_start": f"{params.night_start:02d}:00",
        "night_end": f"{params.night_end:02d}:00",
        "source_url": params.source_url,
        "portal_url": params.portal_url,
    }


@register.inclusion_tag("weather/_gnss_card.html")
def gnss_card():
    return build_gnss_card()
