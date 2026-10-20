"""La franja «Entorno hoy» del panel (LV-358, E2): una sola línea de hechos cargada por htmx.

Reemplaza a las dos tarjetas de `env-row` (el tiempo y el centelleo). No tiene fuente propia: usa la
MISMA ciudad, zona y pronóstico que la cabecera de «Entorno» (`environment_context`), así que ninguna
celda puede contradecir a la pestaña a la que lleva. Cada celda se dibuja solo si la persona tiene el
permiso de SU fuente y su interruptor está encendido; sin ninguna celda no hay franja, ni petición,
ni hueco (el panel lo decide con `environment_strip_enabled`, que usa `cells_for`).

El resumen es de hechos: nada de lo que se arma acá dice si se puede volar (LV-93). La celda de espacio
aéreo no existe todavía: se suma cuando exista la ruta `airspace-map` (bloque E3).
"""

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.core.views import ModelPermissionRequiredMixin
from apps.weather.models import UserWeatherLocation
from apps.weather.panel import current_conditions

from .levels import LEVEL_ORDER
from .tabs import TABS_BY_KEY
from .views import environment_context

# Las celdas que la franja sabe dibujar, en orden. Cada una nace de la pestaña de su fuente: el mismo
# permiso y el mismo interruptor que la pestaña, sin copiarlos.
CELL_KEYS = ("weather", "gnss")


def cells_for(user):
    """Las claves de las celdas que `user` puede ver ahora: permiso de su fuente e interruptor encendido."""
    if not getattr(user, "is_authenticated", False):
        return []
    return [
        key
        for key in CELL_KEYS
        if TABS_BY_KEY[key].enabled() and user.has_perm(TABS_BY_KEY[key].permission)
    ]


def any_cell_switched_on():
    return any(TABS_BY_KEY[key].enabled() for key in CELL_KEYS)


def main_event(events):
    """El evento principal: el de mayor nivel y, a igual nivel, el que empieza antes."""
    if not events:
        return None
    return min(
        events,
        key=lambda e: (
            -LEVEL_ORDER.index(e["level"]),
            e["start"] is None,
            e["start"] or 0,
        ),
    )


def strip_context(user, now=None):
    """Todo lo que dibuja `_strip.html`, calculado acá y no en la plantilla."""
    cells = cells_for(user)
    context = environment_context(user, now)
    summary, forecast = context["env_summary"], context["env_forecast"]
    weather = None
    if "weather" in cells:
        if context["env_location"] is None:
            weather = {"state": "nocity"}
        elif not forecast:
            weather = {"state": "unavailable"}
        else:
            weather = {
                "state": "ok",
                **current_conditions(forecast),
                "event": main_event(summary.events),
                "more_events": max(0, len(summary.events) - 1),
                "line": summary.lines[0],
            }
    return {
        "state": "ok",
        "cells": cells,
        "city": summary.city,
        "weather": weather,
        "gnss": summary.gnss_line if "gnss" in cells else None,
        "hub_url": reverse("environment-hub"),
    }


class EnvironmentStrip(ModelPermissionRequiredMixin, View):
    """GET /environment/strip/: el fragmento de la franja del panel.

    404 si no hay ninguna fuente encendida (no hay ruta que sondear, como el tiempo apagado) y 403 a
    quien no tiene el permiso de ninguna: es «cualquiera de» los de las celdas, así que `has_permission`
    lo resuelve con la misma lista que decide si el panel dibuja el hueco.
    """

    model = UserWeatherLocation
    permission_action = "view"
    template_name = "environment/_strip.html"

    def dispatch(self, request, *args, **kwargs):
        if not any_cell_switched_on():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return bool(cells_for(self.request.user))

    def get(self, request):
        return render(request, self.template_name, strip_context(request.user))
