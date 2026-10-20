"""Tarjeta del tiempo del panel (LV-347): un fragmento htmx, SOLO informativo.

La persona decidió el 2026-10-19 que la tarjeta reemplaza a la decisión de LV-216: muestra el
tiempo y los eventos climáticos previstos en la región de SU ciudad, y no se cruza con permisos,
faenas ni aeronaves. Por eso este módulo no importa nada de `operations` ni de `registry`.

Encendido por omisión desde LV-353 (riesgo de licencia aceptado, ver `docs/dev/tiempo.md`);
`WEATHER_ENABLED=False` lo apaga todo: el panel no pide el fragmento (ver `weather_tags`) y las
tres vistas del tiempo responden 404. Una sola función (`weather_enabled`) decide, para que el
hueco, la vista y el cliente no puedan discrepar.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views import View

from apps.core import weather as weather_client
from apps.core.views import ModelPermissionRequiredMixin
from apps.environment.levels import LEVEL_LABELS

from . import gnss as gnss_module
from . import scene as scene_module
from . import sky as sky_module
from .locations import get_location_for
from .models import UserWeatherLocation


def weather_enabled():
    """El interruptor `WEATHER_ENABLED`; ausente cuenta como encendido, igual que el valor por omisión."""
    return bool(getattr(settings, "WEATHER_ENABLED", True))


class WeatherEnabledMixin:
    """404 antes que cualquier permiso cuando el tiempo está apagado: no hay ruta que sondear."""

    def dispatch(self, request, *args, **kwargs):
        if not weather_enabled():
            raise Http404
        return super().dispatch(request, *args, **kwargs)


CONDITION_LABELS = {
    "clear": pgettext_lazy("weather condition", "Clear"),
    "partly": gettext_lazy("Partly cloudy"),
    "cloudy": gettext_lazy("Cloudy"),
    "fog": gettext_lazy("Fog"),
    "rain": gettext_lazy("Rain"),
    "snow": gettext_lazy("Snow"),
    "storm": gettext_lazy("Thunderstorm"),
    "wind": gettext_lazy("Windy"),
}

EVENT_LABELS = {
    "wind": gettext_lazy("Wind"),
    "gusts": gettext_lazy("Gusts"),
    "heavy_rain": gettext_lazy("Heavy rain"),
    "rain_accumulated": gettext_lazy("Accumulated rain"),
    "thunderstorm": gettext_lazy("Thunderstorm"),
    "hail": gettext_lazy("Hail"),
    "snow": gettext_lazy("Snow"),
    "frost": gettext_lazy("Frost"),
    "heat": gettext_lazy("Heat"),
    "low_visibility": gettext_lazy("Low visibility"),
}

_KMH_PER_UNIT = {"km/h": 1.0, "ms": 3.6, "m/s": 3.6, "mph": 1.609344, "kn": 1.852}
_RAIN_CODES = set(range(51, 68)) | {80, 81, 82}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}
HOURS_SHOWN = 24
STRIP_STEP = 34  # px por hora; la línea de temperatura usa el mismo paso


def condition_slug(code, wind_kmh=None, gust_kmh=None):
    """Uno de los ocho `CONDITION_LABELS` a partir del código WMO (y del viento si el cielo está seco)."""
    if code in (0, 1):
        slug = "clear"
    elif code == 2:
        slug = "partly"
    elif code in (45, 48):
        slug = "fog"
    elif code in _RAIN_CODES:
        slug = "rain"
    elif code in _SNOW_CODES:
        slug = "snow"
    elif code in (95, 96, 99):
        slug = "storm"
    else:
        slug = "cloudy"
    if slug in ("clear", "partly", "cloudy"):
        gust_t = getattr(settings, "WEATHER_EVENT_GUST_KMH", 60)
        wind_t = getattr(settings, "WEATHER_EVENT_WIND_KMH", 40)
        if (gust_kmh or 0) >= gust_t or (wind_kmh or 0) >= wind_t:
            return "wind"
    return slug


def _parse(moment):
    try:
        return datetime.fromisoformat(moment)
    except (TypeError, ValueError):
        return None


def _zone(forecast):
    try:
        return ZoneInfo(forecast.get("timezone") or "")
    except Exception:  # zona desconocida: la del proyecto
        return timezone.get_current_timezone()


def _fake_now(zone):
    """`WEATHER_FAKE_NOW` (ISO) como hora local naive, o `None`.

    Sólo vale con `DEBUG` y `WEATHER_FAKE_FIXTURE` activos, igual que el pronóstico de demostración:
    en producción se ignora aunque esté definida. Sirve para ver cada fase del cielo en el demo.
    """
    raw = (getattr(settings, "WEATHER_FAKE_NOW", "") or "").strip()
    if (
        not raw
        or not settings.DEBUG
        or not getattr(settings, "WEATHER_FAKE_FIXTURE", False)
    ):
        return None
    moment = _parse(raw)
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(zone)
    return moment.replace(tzinfo=None)


def _local_now(forecast):
    zone = _zone(forecast)
    fake = _fake_now(zone)
    if fake is not None:
        return fake
    return timezone.now().astimezone(zone).replace(tzinfo=None)


def _round(value):
    return None if value is None else int(round(value))


def _scaled(value, factor):
    return None if value is None else value * factor


def _hour_rows(forecast, floor, to_kmh):
    rows = [r for r in forecast.get("hourly") or [] if _parse(r.get("time"))]
    upcoming = [r for r in rows if _parse(r["time"]) >= floor]
    picked = (upcoming or rows)[:HOURS_SHOWN]
    hours = []
    for index, row in enumerate(picked):
        moment = _parse(row["time"])
        wind = _scaled(row.get("wind_speed_10m"), to_kmh)
        gust = _scaled(row.get("wind_gusts_10m"), to_kmh)
        prob = row.get("precipitation_probability")
        hours.append(
            {
                "hour": moment.strftime("%H"),
                "x": STRIP_STEP // 2 + index * STRIP_STEP,
                "temp": _round(row.get("temperature_2m")),
                "temp_raw": row.get("temperature_2m"),
                "wind": _round(wind),
                "gust": _round(gust),
                "wind_pct": min(100, round((wind or 0) / 80 * 100)),
                "gust_pct": min(100, round((gust or 0) / 80 * 100)),
                "rain": _round(prob),
                "visibility": row.get("visibility"),
                "title": _(
                    "%(hour)s:00 · %(temp)s °C · wind %(wind)s km/h · gusts %(gust)s km/h"
                    " · rain %(rain)s%%"
                )
                % {
                    "hour": moment.strftime("%H"),
                    "temp": _round(row.get("temperature_2m"))
                    if row.get("temperature_2m") is not None
                    else "–",
                    "wind": _round(wind) if wind is not None else "–",
                    "gust": _round(gust) if gust is not None else "–",
                    "rain": _round(prob) if prob is not None else "–",
                },
            }
        )
    return hours


def _temperature_line(hours):
    """Puntos `x,y` de la polilínea (viewBox de alto 52) y el ancho total de la franja."""
    known = [h for h in hours if h["temp_raw"] is not None]
    if not known:
        return "", len(hours) * STRIP_STEP
    low = min(h["temp_raw"] for h in known)
    high = max(h["temp_raw"] for h in known)
    span = (high - low) or 1
    points = " ".join(
        f"{h['x']},{6 + (high - h['temp_raw']) / span * 40:.1f}" for h in known
    )
    return points, len(hours) * STRIP_STEP


def _day_rows(forecast, today):
    days = []
    for row in forecast.get("daily") or []:
        moment = _parse(row.get("time"))
        if moment is None:
            continue
        lows, highs = row.get("temperature_2m_min"), row.get("temperature_2m_max")
        days.append(
            {
                "date": moment.date(),
                "is_today": moment.date() == today,
                "slug": condition_slug(row.get("weather_code")),
                "tmin": _round(lows),
                "tmax": _round(highs),
                "tmin_raw": lows,
                "tmax_raw": highs,
                "rain": _round(row.get("precipitation_probability_max")),
            }
        )
    known = [d for d in days if d["tmin_raw"] is not None and d["tmax_raw"] is not None]
    if known:
        low = min(d["tmin_raw"] for d in known)
        span = (max(d["tmax_raw"] for d in known) - low) or 1
        for d in known:
            d["bar_left"] = round((d["tmin_raw"] - low) / span * 100)
            d["bar_width"] = max(6, round((d["tmax_raw"] - d["tmin_raw"]) / span * 100))
    for d in days:
        d["label"] = CONDITION_LABELS[d["slug"]]
    return days


def _event_rows(events):
    rows = []
    for event in events:
        symbol, level_label = LEVEL_LABELS.get(event["level"], LEVEL_LABELS["info"])
        rows.append(
            {
                "label": EVENT_LABELS.get(event["type"], event["type"]),
                "level": event["level"],
                "symbol": symbol,
                "level_label": level_label,
                "start": _parse(event["start"]),
                "end": _parse(event["end"]),
                "value": event["value"] if event.get("unit") else None,
                "unit": event.get("unit"),
            }
        )
    return rows


def _checked_at(forecast):
    moment = _parse(forecast.get("fetched_at"))
    if moment is None:
        return ""
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.utc)
    return _("Checked at %(time)s") % {
        "time": timezone.localtime(moment).strftime("%H:%M")
    }


def _scintillation_active(forecast, local_now):
    """¿Está activa la ventana de centelleo GNSS ahora? Sólo un guiño visual: nunca lanza."""
    try:
        if not getattr(settings, "GNSS_SCINTILLATION_ENABLED", True):
            return False
        zone = _zone(forecast)
        sunsets = {}
        for row in forecast.get("daily") or []:
            day = _parse(row.get("time"))
            sunset = _parse(row.get("sunset"))
            if day is not None and sunset is not None:
                sunsets[day.date()] = sunset.replace(tzinfo=zone)
        now = local_now.replace(tzinfo=zone)
        return bool(gnss_module.window_state(now, sunsets=sunsets)["active"])
    except Exception:
        return False


def _now_state(forecast, local_now):
    """Lo que el pronóstico dice de AHORA: condición, viento y si es de día (compartido con la franja)."""
    units = forecast.get("units") or {}
    to_kmh = _KMH_PER_UNIT.get(units.get("wind_speed_10m", "ms"), 3.6)
    current = forecast.get("current") or {}
    daily0 = (forecast.get("daily") or [{}])[0]
    wind = _scaled(current.get("wind_speed_10m"), to_kmh)
    gust = _scaled(current.get("wind_gusts_10m"), to_kmh)
    code = current.get("weather_code")
    if code is None and forecast.get("hourly"):
        code = forecast["hourly"][0].get("weather_code")
    slug = condition_slug(code, wind, gust)
    is_day = current.get("is_day")
    sunrise, sunset = _parse(daily0.get("sunrise")), _parse(daily0.get("sunset"))
    if is_day is None:
        is_day = not (sunrise and sunset and not (sunrise <= local_now <= sunset))
    return {
        "to_kmh": to_kmh,
        "current": current,
        "wind": wind,
        "gust": gust,
        "slug": slug,
        "is_day": bool(is_day),
        "sunrise": sunrise,
        "sunset": sunset,
    }


def current_conditions(forecast):
    """Lo mínimo que dibuja la franja del panel (LV-358, E2): temperatura, condición e icono de día/noche.

    Sale del MISMO cálculo que la tarjeta completa (`_now_state`), de modo que ambas no pueden
    discrepar, y no arma las horas, los días ni la escena del cielo.
    """
    state = _now_state(forecast, _local_now(forecast))
    current = state["current"]
    temp = current.get("temperature_2m")
    if temp is None and forecast.get("hourly"):
        temp = forecast["hourly"][0].get("temperature_2m")
    return {
        "slug": state["slug"],
        "condition": CONDITION_LABELS[state["slug"]],
        "is_night": not state["is_day"],
        "temp": _round(temp),
        "feels": _round(current.get("apparent_temperature")),
    }


def build_card(location, forecast, events):
    """Todo lo que dibuja la tarjeta, calculado aquí y no en la plantilla."""
    local_now = _local_now(forecast)
    now_state = _now_state(forecast, local_now)
    to_kmh = now_state["to_kmh"]
    floor = local_now.replace(minute=0, second=0, microsecond=0)
    hours = _hour_rows(forecast, floor, to_kmh)
    days = _day_rows(forecast, local_now.date())
    current = now_state["current"]
    first = hours[0] if hours else {}
    wind, gust = now_state["wind"], now_state["gust"]
    slug, is_day = now_state["slug"], now_state["is_day"]
    sunrise, sunset = now_state["sunrise"], now_state["sunset"]
    temp = current.get("temperature_2m")
    direction = current.get("wind_direction_10m")
    points, strip_width = _temperature_line(hours)
    visibility = first.get("visibility")
    sky = sky_module.sky_state(
        local_now, forecast.get("daily"), is_day, slug, _zone(forecast)
    )
    scintillation = _scintillation_active(forecast, local_now)
    return {
        "state": "ok",
        "city": location.label,
        "slug": slug,
        "condition": CONDITION_LABELS[slug],
        "is_day": bool(is_day),
        "is_night": not is_day,
        "temp": _round(temp if temp is not None else first.get("temp_raw")),
        "feels": _round(current.get("apparent_temperature")),
        "wind": _round(wind),
        "gust": _round(gust),
        "wind_dir": _round(direction),
        "wind_rot": None if direction is None else round((direction + 180) % 360),
        "cloud": _round(current.get("cloud_cover")),
        "visibility_km": None if visibility is None else round(visibility / 1000, 1),
        "sunrise": sunrise,
        "sunset": sunset,
        "sky": sky,
        "scene": scene_module.scene_context(sky, local_now, scintillation),
        "hours": hours,
        "temp_points": points,
        "strip_width": strip_width,
        "days": days,
        "events": _event_rows(events),
        "checked_at": _checked_at(forecast),
    }


class WeatherPanel(WeatherEnabledMixin, ModelPermissionRequiredMixin, View):
    """GET /weather/panel/: el fragmento de la tarjeta. Ver exige `view_userweatherlocation`."""

    model = UserWeatherLocation
    permission_action = "view"
    template_name = "weather/_panel_card.html"

    def get(self, request):
        location = get_location_for(request.user)
        if location is None:
            return self._render(request, {"state": "empty"})
        forecast = weather_client.panel_forecast(location.latitude, location.longitude)
        if forecast is None:
            return self._render(request, {"state": "error", "city": location.label})
        events = weather_client.regional_events(forecast)
        return self._render(request, build_card(location, forecast, events))

    def _render(self, request, context):
        # LV-358: dentro de «Entorno» la advertencia «Referencial» es una sola y vive en la
        # cabecera común; la pestaña lo pide con `?embed=environment` para no repetirla (y el
        # botón de reintentar conserva el parámetro).
        context["hide_legend"] = request.GET.get("embed") == "environment"
        return render(request, self.template_name, context)
