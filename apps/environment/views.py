"""La sección «Entorno» (LV-358): tiempo y centelleo GNSS en un conjunto, sin modelos.

Cada pestaña es una ruta real con su permiso de modelo (LV-268); el concentrador `/environment/`
redirige a la primera pestaña permitida y da 403 si no hay ninguna («cualquiera de»). No hay tenant
acá: el tiempo es de la persona (`UserWeatherLocation` de `request.user`) y el centelleo es una
estadística global; no se lee ninguna fila de otra persona.
"""

from datetime import datetime

from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.core import weather as weather_client
from apps.core.views import ModelPermissionRequiredMixin
from apps.weather import gnss
from apps.weather.locations import get_location_for
from apps.weather.models import UserWeatherLocation
from apps.weather.panel import weather_enabled
from apps.weather.templatetags.gnss_tags import gnss_card_enabled

from .airspace_near import airspace_near_fact
from .gnss_day import day_geometry, season_geometry
from .summary import build_summary, season_label
from .tabs import TABS_BY_KEY, tabs_for


def _checked_at(forecast):
    """Cuándo se consultó el pronóstico (aware), o `None`."""
    try:
        moment = datetime.fromisoformat(forecast.get("fetched_at"))
    except (AttributeError, TypeError, ValueError):
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.utc)
    return moment


def environment_context(user, now=None):
    """Lo común a todas las pestañas: la ciudad, UN pronóstico y el resumen que sale de él."""
    now = now or timezone.now()
    location = get_location_for(user)
    forecast, events = None, []
    if location is not None and weather_enabled():
        forecast = weather_client.panel_forecast(location.latitude, location.longitude)
        if forecast:
            events = weather_client.regional_events(forecast)
    # El tercer renglón y la celda de la franja salen de ESTE hecho (una sola función, E3).
    airspace = (
        airspace_near_fact(user, now=now) if TABS_BY_KEY["airspace"].enabled() else None
    )
    summary = build_summary(
        now,
        forecast,
        events,
        location.label if location else "",
        gnss_enabled=gnss_card_enabled(),
        forecast_checked_at=_checked_at(forecast) if forecast else None,
        airspace=airspace,
    )
    return {
        "env_location": location,
        "env_summary": summary,
        "env_forecast": forecast,
        "env_tabs": tabs_for(user),
    }


class EnvironmentHub(ModelPermissionRequiredMixin, View):
    """GET /environment/: lleva a la primera pestaña permitida, o 403 si no hay ninguna.

    El permiso es «cualquiera de» los de las pestañas, así que no hay un único `view_*` que pedir:
    `has_permission` lo resuelve con la misma lista que dibuja el menú.
    """

    model = UserWeatherLocation
    permission_action = "view"

    def has_permission(self):
        return bool(tabs_for(self.request.user))

    def get(self, request):
        return redirect(tabs_for(request.user)[0]["url"])


class EnvironmentTab(ModelPermissionRequiredMixin, View):
    """Una pestaña: 404 si está apagada, 403 sin el permiso de SU fuente."""

    model = UserWeatherLocation
    permission_action = "view"
    tab_key = None
    template_name = None

    @property
    def tab(self):
        return TABS_BY_KEY[self.tab_key]

    def dispatch(self, request, *args, **kwargs):
        if not self.tab.enabled():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return self.request.user.has_perm(self.tab.permission)

    def extra_context(self, request, context):
        return {}

    def get(self, request):
        context = environment_context(request.user)
        context["env_active"] = self.tab_key
        context.update(self.extra_context(request, context))
        return render(request, self.template_name, context)


class EnvironmentWeatherTab(EnvironmentTab):
    """El tiempo: la tarjeta completa se carga por htmx, como en el panel (LV-353)."""

    tab_key = "weather"
    template_name = "environment/weather_tab.html"


class EnvironmentGnssTab(EnvironmentTab):
    """El centelleo: explica, y el estado vivo sale de la cabecera común."""

    tab_key = "gnss"
    template_name = "environment/gnss_tab.html"

    def extra_context(self, request, context):
        params = gnss.params_from_settings()
        summary = context["env_summary"]
        season = season_geometry(summary.now, params)
        return {
            "gnss_day": day_geometry(
                summary.now, summary.sunsets, summary.sunrises, params
            ),
            "gnss_months": season["months"],
            "gnss_years": season["years"],
            "gnss_current_active": season["current_active"],
            "gnss_season": season_label(params),
            "gnss_year_from": params.year_from,
            "gnss_year_to": params.year_to,
            "gnss_sunset_offset": params.sunset_offset_min,
        }
