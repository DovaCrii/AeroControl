"""Adaptador de MET Norway (`locationforecast/2.0/complete`) a la forma que ya usa el panel (LV-365).

El panel, la ventana de centelleo, el resumen de «Entorno» y `regional_events()` leen el diccionario
que produce `weather._parse_panel` a partir de la respuesta de Open-Meteo (columnas por hora y por
día, horas locales «YYYY-MM-DDTHH:MM», `weather_code` WMO). Este módulo NO inventa otra forma:
convierte la respuesta de MET en un cuerpo con la forma de Open-Meteo y deja que `_parse_panel` lo
procese, así que lo de abajo no cambia con el proveedor.

Forma real de la respuesta (medida el 2026-10-23 para Santiago, `complete`): ~61 KB sin comprimir y
88 pasos: horarios las primeras ~60 h y cada 6 h hasta ~9 días. Cada paso trae `instant.details`
(temperatura, temperatura aparente, nubosidad, humedad, viento y su dirección, UV de cielo despejado)
y, según el tramo, `next_1_hours` / `next_6_hours` / `next_12_hours` con `summary.symbol_code` y la
precipitación acumulada. Fuera de los países nórdicos NO vienen ráfagas, probabilidad de
precipitación ni visibilidad: quedan en `None` y la interfaz dice «no disponible»; nada se estima.
`ultraviolet_index_clear_sky` es el UV con cielo despejado, no el pronóstico, así que no se usa como
`uv_index_max` (sería un número más alto que el real).

Pérdidas conocidas, a propósito y documentadas:

- `symbol_code` → WMO es una tabla fija con menos detalle (ver `SYMBOL_TO_WMO`): la llovizna no
  existe en MET (la lluvia ligera sale como 61); el aguanieve sale como lluvia helada (66/67) y sus
  chubascos como chubascos de lluvia (81); toda tormenta («thunder») sale como 95; no hay granizo.
- El día en curso resume lo que falta del día (MET empieza en la hora actual), no el día completo.
- La precipitación de un paso de 6 h se atribuye al día local en que empieza.
- El código diario es el MÁS SEVERO (el mayor WMO) de los pasos del día, como hace Open-Meteo.
- El amanecer y la puesta no vienen de MET: los pone `weather._with_local_sun` (módulo solar).
"""

import math
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import solar

HOURS = 48
DAYS = 7

# `symbol_code` sin el sufijo _day/_night/_polartwilight → código WMO 4677.
SYMBOL_TO_WMO = {
    "clearsky": 0,
    "fair": 1,
    "partlycloudy": 2,
    "cloudy": 3,
    "fog": 45,
    "lightrain": 61,
    "rain": 63,
    "heavyrain": 65,
    "lightrainshowers": 80,
    "rainshowers": 81,
    "heavyrainshowers": 82,
    "lightsleet": 66,
    "sleet": 67,
    "heavysleet": 67,
    "lightsleetshowers": 81,
    "sleetshowers": 81,
    "heavysleetshowers": 82,
    "lightsnow": 71,
    "snow": 73,
    "heavysnow": 75,
    "lightsnowshowers": 85,
    "snowshowers": 85,
    "heavysnowshowers": 86,
}
_THUNDER_WMO = 95
_SUFFIXES = ("_day", "_night", "_polartwilight")


def wmo_for_symbol(symbol):
    """Código WMO de un `symbol_code` de MET, o `None` si falta o no se conoce (nada se inventa)."""
    if not isinstance(symbol, str) or not symbol:
        return None
    base = symbol
    for suffix in _SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if "thunder" in base:
        return _THUNDER_WMO
    return SYMBOL_TO_WMO.get(base)


def zone_for(latitude, longitude, hint=None):
    """Nombre de zona horaria IANA: la `hint` si es válida; si no, por coordenadas en Chile.

    Sin pista y fuera de Chile queda `UTC`: las horas se muestran en UTC antes que en una zona
    inventada. Chile: Isla de Pascua (`Pacific/Easter`), Magallanes (`America/Punta_Arenas`, desde
    los 48°S) y el resto del continente `America/Santiago`.
    """
    if isinstance(hint, str) and hint.strip():
        try:
            ZoneInfo(hint.strip())
            return hint.strip()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    if -56.0 <= latitude <= -17.0:
        if -110.0 <= longitude <= -105.0 and -30.0 <= latitude <= -26.0:
            return "Pacific/Easter"
        if -76.0 <= longitude <= -66.0:
            return "America/Punta_Arenas" if latitude <= -48.0 else "America/Santiago"
    return "UTC"


def _number(value):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return value if ok and math.isfinite(value) else None


def _details(block):
    details = block.get("details") if isinstance(block, dict) else None
    return details if isinstance(details, dict) else {}


def _symbol(block):
    summary = block.get("summary") if isinstance(block, dict) else None
    return summary.get("symbol_code") if isinstance(summary, dict) else None


def _steps(payload):
    """Pasos `[(instante UTC, data)]` ordenados; descarta los que no se leen."""
    props = payload.get("properties") if isinstance(payload, dict) else None
    series = props.get("timeseries") if isinstance(props, dict) else None
    if not isinstance(series, list):
        return []
    steps = []
    for item in series:
        if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
            continue
        try:
            moment = datetime.fromisoformat(
                str(item.get("time")).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if moment.tzinfo is None:
            continue
        steps.append((moment.astimezone(dt_timezone.utc), item["data"]))
    steps.sort(key=lambda step: step[0])
    return steps


def _local(moment, zone):
    return moment.astimezone(zone).strftime("%Y-%m-%dT%H:%M")


def _hour_code(data):
    for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
        code = wmo_for_symbol(_symbol(data.get(key)))
        if code is not None:
            return code
    return None


def to_open_meteo(payload, zone_name, latitude, longitude):
    """Cuerpo con la forma de Open-Meteo a partir de la respuesta de MET, o `None` si no sirve."""
    steps = _steps(payload)
    if not steps:
        return None
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None

    hourly = {
        key: []
        for key in (
            "time",
            "temperature_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation_probability",
            "precipitation",
            "visibility",
            "weather_code",
        )
    }
    days = {}  # fecha local -> acumuladores

    def bucket(moment):
        key = moment.astimezone(zone).date().isoformat()
        return days.setdefault(
            key,
            {
                "temps": [],
                "winds": [],
                "gusts": [],
                "probs": [],
                "rain": 0.0,
                "rain_seen": False,
                "codes": [],
            },
        )

    covered_until = None
    for moment, data in steps:
        instant = _details(data.get("instant"))
        temp = _number(instant.get("air_temperature"))
        wind = _number(instant.get("wind_speed"))
        gust = _number(instant.get("wind_speed_of_gust"))
        one, six = data.get("next_1_hours"), data.get("next_6_hours")
        acc = bucket(moment)
        if temp is not None:
            acc["temps"].append(temp)
        if wind is not None:
            acc["winds"].append(wind)
        if gust is not None:
            acc["gusts"].append(gust)
        code = _hour_code(data)
        if code is not None:
            acc["codes"].append(code)
        for block in (six,):
            details = _details(block)
            for key in ("air_temperature_max", "air_temperature_min"):
                value = _number(details.get(key))
                if value is not None:
                    acc["temps"].append(value)
        if isinstance(one, dict) and len(hourly["time"]) < HOURS:
            details = _details(one)
            hourly["time"].append(_local(moment, zone))
            hourly["temperature_2m"].append(temp)
            hourly["wind_speed_10m"].append(wind)
            hourly["wind_gusts_10m"].append(gust)
            hourly["precipitation_probability"].append(
                _number(details.get("probability_of_precipitation"))
            )
            hourly["precipitation"].append(_number(details.get("precipitation_amount")))
            hourly["visibility"].append(None)
            hourly["weather_code"].append(wmo_for_symbol(_symbol(one)))
        # Precipitación: un solo bloque por tramo de tiempo, para no contar dos veces la misma lluvia.
        if covered_until is not None and moment < covered_until:
            continue
        for block, span in ((one, 1), (six, 6)):
            if not isinstance(block, dict):
                continue
            details = _details(block)
            amount = _number(details.get("precipitation_amount"))
            prob = _number(details.get("probability_of_precipitation"))
            if prob is not None:
                acc["probs"].append(prob)
            if amount is not None:
                acc["rain"] += amount
                acc["rain_seen"] = True
            covered_until = moment + timedelta(hours=span)
            break

    first_moment, first_data = steps[0]
    first = _details(first_data.get("instant"))
    daylight = solar.is_daylight(first_moment, latitude, longitude, zone)
    one = first_data.get("next_1_hours")
    current = {
        "temperature_2m": _number(first.get("air_temperature")),
        "apparent_temperature": _number(first.get("apparent_air_temperature")),
        "wind_speed_10m": _number(first.get("wind_speed")),
        "wind_gusts_10m": _number(first.get("wind_speed_of_gust")),
        "wind_direction_10m": _number(first.get("wind_from_direction")),
        "precipitation": _number(_details(one).get("precipitation_amount")),
        "cloud_cover": _number(first.get("cloud_area_fraction")),
        "weather_code": _hour_code(first_data),
        "is_day": None if daylight is None else int(daylight),
    }

    daily = {
        key: []
        for key in (
            "time",
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "uv_index_max",
        )
    }
    for key in sorted(days)[:DAYS]:
        acc = days[key]
        daily["time"].append(key)
        daily["weather_code"].append(max(acc["codes"]) if acc["codes"] else None)
        daily["temperature_2m_max"].append(max(acc["temps"]) if acc["temps"] else None)
        daily["temperature_2m_min"].append(min(acc["temps"]) if acc["temps"] else None)
        daily["precipitation_sum"].append(
            round(acc["rain"], 1) if acc["rain_seen"] else None
        )
        daily["precipitation_probability_max"].append(
            max(acc["probs"]) if acc["probs"] else None
        )
        daily["wind_speed_10m_max"].append(max(acc["winds"]) if acc["winds"] else None)
        daily["wind_gusts_10m_max"].append(max(acc["gusts"]) if acc["gusts"] else None)
        daily["uv_index_max"].append(None)

    return {
        "timezone": zone_name,
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s"},
        "hourly_units": {
            "temperature_2m": "°C",
            "wind_speed_10m": "m/s",
            "wind_gusts_10m": "m/s",
            "precipitation": "mm",
            "visibility": "m",
        },
        "daily_units": {"precipitation_sum": "mm", "wind_speed_10m_max": "m/s"},
        "current": current,
        "hourly": hourly,
        "daily": daily,
    }


def missing_fields(parsed):
    """Qué magnitudes NO trajo esta respuesta en ninguna hora ni día, para decirlo en la tarjeta.

    Devuelve un subconjunto ordenado de `("gusts", "visibility", "rain_probability")`.
    """
    hours = parsed.get("hourly") or []
    days = parsed.get("daily") or []
    current = parsed.get("current") or {}
    missing = []
    if not any(h.get("wind_gusts_10m") is not None for h in hours) and (
        current.get("wind_gusts_10m") is None
    ):
        missing.append("gusts")
    if not any(h.get("visibility") is not None for h in hours):
        missing.append("visibility")
    if not any(
        h.get("precipitation_probability") is not None for h in hours
    ) and not any(d.get("precipitation_probability_max") is not None for d in days):
        missing.append("rain_probability")
    return missing
