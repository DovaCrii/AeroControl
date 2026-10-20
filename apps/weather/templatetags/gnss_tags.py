"""Etiquetas de plantilla de la tarjeta «Centelleo GNSS» (LV-352, fase 2).

La tarjeta es SOLO informativa: una referencia estadística tomada de GEOCOM (portal
`centelleo.geocom.cl`, operado con el área de desarrollo de Trimble). No llama a nadie, no lee
datos en vivo y no se cruza con permisos, faenas ni aeronaves. La ventana se calcula en
`apps/weather/gnss.py`; aquí sólo se arma lo que dibuja la plantilla. Se apaga con
`GNSS_SCINTILLATION_ENABLED=False`.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django import template
from django.conf import settings
from django.utils import timezone

from apps.core import weather as weather_client
from apps.weather import gnss
from apps.weather.locations import default_location

register = template.Library()


@register.simple_tag
def gnss_card_enabled():
    """¿Se dibuja la tarjeta? Sólo depende del interruptor (encendido por omisión)."""
    return bool(getattr(settings, "GNSS_SCINTILLATION_ENABLED", True))


def forecast_sunsets():
    """`({fecha: puesta de sol aware}, ciudad, zona)` del pronóstico de la ciudad por omisión.

    Es la de `WEATHER_DEFAULT_*`, no la de la persona: el panel tiene un presupuesto exacto de
    consultas (`LV-237`) y leer la fila de la ciudad de cada quien sumaría una. La ventana es una
    referencia estadística de todo el norte y centro de Chile, no una medición local.

    LV-354: nunca lanza. Sin ciudad, sin pronóstico o con una puesta ilegible la ventana vuelve a
    las horas fijas, y la tarjeta no muestra la línea del atardecer.
    """
    try:
        location = default_location()
        forecast = weather_client.panel_forecast(location.latitude, location.longitude)
        if not forecast:
            return {}, "", None
        try:
            zone = ZoneInfo(forecast.get("timezone") or "")
        except Exception:  # zona desconocida: la del proyecto
            zone = ZoneInfo(settings.TIME_ZONE)
        sunsets = {}
        for row in forecast.get("daily") or []:
            day = datetime.fromisoformat(row["time"]).date()
            sunsets[day] = datetime.fromisoformat(row["sunset"]).replace(tzinfo=zone)
        return sunsets, location.label, zone
    except Exception:
        return {}, "", None


def build_gnss_card(now=None):
    """Todo lo que dibuja la tarjeta, calculado aquí y no en la plantilla."""
    params = gnss.params_from_settings()
    now = now or timezone.now()
    sunsets, city, zone = forecast_sunsets()
    state = gnss.window_state(now, params, sunsets)
    today = now.astimezone(zone or ZoneInfo(settings.TIME_ZONE)).date()
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
    return build_gnss_card()
