"""Etiquetas de plantilla de la tarjeta «Centelleo GNSS» (LV-352, fase 2).

La tarjeta es SOLO informativa: una referencia estadística tomada de GEOCOM (portal
`centelleo.geocom.cl`, operado con el área de desarrollo de Trimble). No llama a nadie, no lee
datos en vivo y no se cruza con permisos, faenas ni aeronaves. La ventana se calcula en
`apps/weather/gnss.py`; aquí sólo se arma lo que dibuja la plantilla. Se apaga con
`GNSS_SCINTILLATION_ENABLED=False`.

LV-358: `build_gnss_card` es una función PURA `(now, sunsets, city)`: no pide el pronóstico por su
cuenta. Antes la tarjeta del panel llamaba a `panel_forecast()` mientras se armaba la página (con
la caché fría, una salida a la red de hasta 4 s que ninguna prueba de consultas veía) y lo hacía
para la ciudad por omisión, no la de la persona, de modo que la puesta de la tarjeta del tiempo y
la del centelleo podían contradecirse. Ahora quien tiene el pronóstico (la sección «Entorno») se lo
pasa; la etiqueta del panel no tiene ninguno y usa las horas fijas.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django import template
from django.conf import settings
from django.utils import timezone

from apps.weather import gnss

register = template.Library()


@register.simple_tag
def gnss_card_enabled():
    """¿Se dibuja la tarjeta? Sólo depende del interruptor (encendido por omisión)."""
    return bool(getattr(settings, "GNSS_SCINTILLATION_ENABLED", True))


def _zone_of(sunsets):
    for moment in (sunsets or {}).values():
        if moment.tzinfo is not None:
            return moment.tzinfo
    return ZoneInfo(settings.TIME_ZONE)


def build_gnss_card(now, sunsets=None, city=""):
    """Todo lo que dibuja la tarjeta, calculado aquí y no en la plantilla.

    `sunsets` es `{fecha: puesta aware}` de UN pronóstico y `city` el nombre de su ciudad; ambos
    vacíos significan «sin pronóstico»: la ventana usa las horas fijas y no hay línea de puesta.
    """
    sunsets = sunsets or {}
    params = gnss.params_from_settings()
    state = gnss.window_state(now, params, sunsets)
    zone = _zone_of(sunsets)
    today = now.astimezone(zone).date()
    sunset = sunsets.get(today)
    dusk = sunset + timedelta(minutes=params.sunset_offset_min) if sunset else None
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
        # Texto ya en la hora de la ciudad del pronóstico (el filtro `date` usaría la del proyecto).
        "sunset": sunset.strftime("%H:%M") if sunset else None,
        "dusk": dusk.astimezone(zone).strftime("%H:%M") if dusk else None,
        "sunset_city": city,
        "source_url": params.source_url,
        "portal_url": params.portal_url,
    }


@register.inclusion_tag("weather/_gnss_card.html")
def gnss_card():
    """La tarjeta del panel: sin pronóstico propio, con las horas fijas (ver el docstring del módulo)."""
    return build_gnss_card(timezone.now())
