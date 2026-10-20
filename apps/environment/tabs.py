"""Las pestañas de «Entorno» (LV-358): una lista, un permiso por pestaña, un solo lugar donde sumar otra.

Cada pestaña es una ruta real. Una persona ve una pestaña si (1) tiene el permiso de modelo de su
fuente, (2) la pestaña está encendida (sus interruptores `WEATHER_ENABLED` /
`GNSS_SCINTILLATION_ENABLED`) y (3) su ruta existe. El tercero es el punto de extensión: la pestaña
«Espacio aéreo» ya está declarada acá y aparece sola cuando otro bloque registre `airspace-map`;
mientras la ruta no exista, ni siquiera quien tiene `view_airspacefeature` (ni un superusuario) ve
un enlace roto.
"""

from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy


def _weather_on():
    return bool(getattr(settings, "WEATHER_ENABLED", True))


def _gnss_on():
    return bool(getattr(settings, "GNSS_SCINTILLATION_ENABLED", True))


def _always():
    return True


@dataclass(frozen=True)
class Tab:
    key: str
    url_name: str
    label: object
    permission: str
    enabled: Callable[[], bool] = _always


TABS = (
    Tab(
        "weather",
        "environment-weather",
        gettext_lazy("Weather"),
        "weather.view_userweatherlocation",
        _weather_on,
    ),
    Tab(
        "gnss",
        "environment-gnss",
        gettext_lazy("GNSS scintillation"),
        "weather.view_userweatherlocation",
        _gnss_on,
    ),
    # Otro bloque registra la ruta `airspace-map` (`/environment/airspace/`); hasta entonces no se
    # muestra.
    Tab(
        "airspace",
        "airspace-map",
        gettext_lazy("Airspace"),
        "airspace.view_airspacefeature",
    ),
)

TABS_BY_KEY = {tab.key: tab for tab in TABS}


def _url(tab):
    try:
        return reverse(tab.url_name)
    except NoReverseMatch:
        return None


def tabs_for(user):
    """`[{key, label, url}]` de las pestañas que `user` puede abrir, en orden."""
    if not getattr(user, "is_authenticated", False):
        return []
    found = []
    for tab in TABS:
        if not tab.enabled() or not user.has_perm(tab.permission):
            continue
        url = _url(tab)
        if url:
            found.append({"key": tab.key, "label": tab.label, "url": url})
    return found
