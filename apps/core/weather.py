"""Weather forecast for a flight area (R8.1, ISO 8.1 meteorological review).

This is the project's **first and only outgoing HTTP call**, so the design is
deliberately conservative -- the four concerns MASTER_PLAN named, and how each
is resolved:

- **CSP**: the call happens *server-side*, never from the browser, so the
  policy stays a bare `default-src 'self'` with no `connect-src` exception.
  Fetching from the page would have meant opening the CSP to a third-party
  origin for every user on every page load.
- **Secrets**: Open-Meteo needs no API key or registration, so there is no
  credential to store, rotate, or leak into a template. That is the main
  reason it was picked over AccuWeather/OpenWeather/UAV Forecast, all of
  which require a key.
- **Cache**: one call per (rounded coordinate, date) per CACHE_SECONDS.
  Weather does not change per request, and a page reload must not become a
  third-party request. Coordinates are rounded to ~1 km so that two plans
  over the same site share a cache entry.
- **Degradation**: every failure path -- disabled, timeout, HTTP error,
  malformed payload -- returns None. The caller renders "unavailable"; a
  provider outage never breaks a page or blocks a flight record. Timeout is
  short on purpose: a slow third party must not hold a worker.

Disabled by default (`WEATHER_ENABLED=False`): a deployment that never sets
it keeps the project's zero-outgoing-calls property.
"""

import hashlib
import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import solar, weather_met

logger = logging.getLogger("aerocontrol.weather")

# Bounded read of a provider response. Medido el 2026-10-23: `locationforecast/2.0/complete` de MET
# Norway para Santiago pesa ~61 KB sin comprimir (88 pasos); Open-Meteo ~20 KB. El tope deja
# cuatro veces ese margen para sitios con más variables (países nórdicos) sin ser ilimitado.
MAX_BODY_BYTES = 256 * 1024

# LV-365 (decisión de la persona, 2026-10-21): la API gratuita de Open-Meteo es de uso NO comercial,
# así que el proveedor por omisión es MET Norway (NLOD 2.0 y CC BY 4.0, uso comercial permitido, sin
# llave). `open_meteo` queda para quien tenga plan de pago o servidor propio (`WEATHER_API_URL`).
PROVIDER_MET = "met_norway"
PROVIDER_OPEN_METEO = "open_meteo"
KEY_PARAM_BY_PROVIDER = {PROVIDER_OPEN_METEO: "apikey"}
PROVIDER_CREDITS = {
    PROVIDER_MET: {
        "slug": PROVIDER_MET,
        "name": "MET Norway",
        "url": "https://www.met.no/en",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
    PROVIDER_OPEN_METEO: {
        "slug": PROVIDER_OPEN_METEO,
        "name": "Open-Meteo.com",
        "url": "https://open-meteo.com/",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
}
# Mientras MET contesta 429 no se le vuelve a preguntar; la copia vieja se sigue sirviendo.
MET_BACKOFF_SECONDS = 15 * 60
# La copia cruda se guarda más que el pronóstico, para poder preguntar «¿cambió?» (304).
MET_RAW_CACHE_SECONDS = 6 * 3600


def provider():
    """El proveedor activo (`WEATHER_PROVIDER`); un valor desconocido cae en MET Norway."""
    value = (
        str(getattr(settings, "WEATHER_PROVIDER", PROVIDER_MET) or "").strip().lower()
    )
    return value if value in PROVIDER_CREDITS else PROVIDER_MET


def provider_credit(slug=None):
    """Quién es el proveedor y bajo qué licencia, para la atribución que cada pantalla dibuja.

    `slug` es el proveedor que produjo ESE pronóstico (`forecast["provider"]`): una copia en caché
    de otro proveedor se atribuye a quien la dio, no al que esté configurado hoy.
    """
    return dict(PROVIDER_CREDITS[slug if slug in PROVIDER_CREDITS else provider()])


def _met_user_agent():
    return str(getattr(settings, "WEATHER_USER_AGENT", "") or "").strip()


# The daily fields ISO 8.1 actually asks about: wind (the limiting factor for
# an RPAS), gusts, and precipitation. Requested as a fixed list, not built
# from user input.
#
# R8.4: temperature joined the list. It is *not* a second call -- Open-Meteo
# returns every requested daily field in the same response, so this costs one
# extra query parameter and nothing else (same cache entry, same timeout, same
# failure paths). Listed first because that is the reading order the card uses.
DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "precipitation_sum",
    "precipitation_probability_max",
    # LV-89: the UV index rides in the same response. Operationally it belongs
    # next to the daylight window below -- both describe the sun, and a crew
    # working a full day outdoors is the reason to show it.
    "uv_index_max",
)

# LV-89: the daylight window, asked for at the user's request. Kept apart from
# DAILY_FIELDS because the provider returns these as **ISO timestamps, not
# numbers**, and `_parse`'s numeric guard would drop them silently.
#
# Not decoration: the insurance certificate for these aircraft states "JORNADA
# DE OPERACIÓN: DIURNA", so flying outside this window is a **coverage**
# problem, not a comfort one. And like the temperature, it costs no extra call.
DAYLIGHT_FIELDS = ("sunrise", "sunset")

# R8.4: asked for alongside DAILY_FIELDS but deliberately *not* one of them --
# it is a condition code, not a measurement, so it must not count towards "the
# provider answered with something usable" (see _parse). A response carrying
# only a weather code and no numbers is not a forecast.
CONDITION_FIELD = "weather_code"

# R8.4, at the user's request: wind in m/s, not the provider's default km/h.
# This is the unit the aircraft are specified in -- DJI publishes maximum wind
# resistance in m/s -- so a pilot comparing the forecast against the airframe's
# limit does not have to convert in their head, which is how a go/no-go call
# gets made wrong. Open-Meteo reports the unit it used in `daily_units`, and
# the card prints that back, so the number is never shown bare.
WIND_SPEED_UNIT = "ms"

# WMO 4677 weather codes, collapsed into the conditions worth telling apart
# before a flight. The value is a plain slug (never a translated string): it
# gets cached, and a cached label would freeze whichever language happened to
# render first. The template maps slug -> icon + wording, where the literal is
# extractable by makemessages (AGENTS.md forbids `_(variable)`).
CONDITION_CODES = {
    "clear": (0,),
    "partly_cloudy": (1, 2),
    "cloudy": (3,),
    "fog": (45, 48),
    "drizzle": (51, 53, 55, 56, 57),
    "rain": (61, 63, 65, 66, 67, 80, 81, 82),
    "snow": (71, 73, 75, 77, 85, 86),
    "thunderstorm": (95, 96, 99),
}


def condition_for(code):
    """Slug for a WMO weather code, or None when it is absent/unknown.

    Unknown returns None rather than a catch-all "cloudy": inventing a
    condition the provider did not report would put a wrong picture next to
    real numbers.
    """
    if not isinstance(code, (int, float)) or isinstance(code, bool):
        return None
    for slug, codes in CONDITION_CODES.items():
        if int(code) in codes:
            return slug
    return None


def _rounded(value):
    """~1 km precision: enough for a forecast, and it makes two plans over the
    same site share one cache entry instead of one per bbox centroid."""
    return round(float(value), 2)


def bbox_centroid(version):
    """(latitude, longitude) at the middle of a GeoPlanVersion's bbox, or None.

    The bbox is already stored on the version (a derived column, so no need to
    deserialize the canonical document just to locate the area).
    """
    if version is None:
        return None
    west, south = version.bbox_west, version.bbox_south
    east, north = version.bbox_east, version.bbox_north
    if None in (west, south, east, north):
        return None
    return ((south + north) / 2, (west + east) / 2)


def forecast_for(latitude, longitude, target_date):
    """Daily forecast for one place and day, or None when unavailable.

    Never raises: this feeds a page that must render with or without it.
    """
    if not getattr(settings, "WEATHER_ENABLED", False):
        return None
    try:
        latitude, longitude = _rounded(latitude), _rounded(longitude)
    except (TypeError, ValueError):
        return None

    iso_date = target_date.isoformat()
    if provider() == PROVIDER_MET:
        # MET no tiene consulta «por fecha»: la fila del día sale del MISMO pronóstico del panel
        # (una sola llamada por ubicación) y sólo existe dentro de sus 7 días.
        return _day_from_panel(panel_forecast(latitude, longitude), iso_date)
    # The wind unit is part of the key: changing WIND_SPEED_UNIT must not serve
    # numbers fetched in the old unit under the new label for up to an hour.
    cache_key = f"weather:{latitude}:{longitude}:{iso_date}:{WIND_SPEED_UNIT}"
    cached = cache.get(cache_key)
    if cached is not None:
        # A cached miss is stored as the sentinel below, so a provider that is
        # down does not get hammered once per page view.
        return None if cached == "unavailable" else cached

    payload = _fetch(latitude, longitude, iso_date)
    parsed = _parse(payload, iso_date) if payload is not None else None
    cache.set(
        cache_key,
        parsed if parsed is not None else "unavailable",
        getattr(settings, "WEATHER_CACHE_SECONDS", 3600),
    )
    return parsed


def _day_from_panel(forecast, iso_date):
    """La forma de `forecast_for` (la de `_parse`) a partir de una fila diaria del pronóstico."""
    if not isinstance(forecast, dict):
        return None
    row = next(
        (r for r in forecast.get("daily") or [] if r.get("time") == iso_date), None
    )
    if row is None:
        return None
    result = {field: row.get(field) for field in DAILY_FIELDS}
    if all(entry is None for entry in result.values()):
        return None
    result["condition"] = condition_for(row.get("weather_code"))
    result["fetched_at"] = forecast.get("fetched_at")
    sunrise, sunset = (
        str(row.get(field))[11:16] if row.get(field) else None
        for field in DAYLIGHT_FIELDS
    )
    result["daylight"] = (
        {"sunrise": sunrise, "sunset": sunset} if sunrise and sunset else None
    )
    result["units"] = forecast.get("units") or {}
    result["date"] = iso_date
    return result


def _fetch(latitude, longitude, iso_date):
    return _get_json(
        settings.WEATHER_API_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(DAILY_FIELDS + (CONDITION_FIELD,) + DAYLIGHT_FIELDS),
            "wind_speed_unit": WIND_SPEED_UNIT,
            "timezone": "auto",
            "start_date": iso_date,
            "end_date": iso_date,
        },
    )


class _Reply(NamedTuple):
    """Lo que contestó el proveedor: estado, cuerpo ya decodificado y cabeceras en minúsculas."""

    status: int
    payload: object
    headers: dict


def _key_param():
    """Nombre del parámetro de llave del proveedor activo, o `None` si no usa llave (LV-365)."""
    return KEY_PARAM_BY_PROVIDER.get(provider())


def _exchange(base, params, headers=None, with_key=True):
    """GET `base?params`: un `_Reply`, o None si no hubo respuesta usable. Never raises.

    The base URL is a setting, never user input, and the query is built from
    validated values plus fixed field names -- nothing user-controlled reaches
    the request except the (length-bounded) place search text, which is only
    ever URL-encoded into a query value (no SSRF surface).

    The optional `WEATHER_API_KEY` is added here, con el nombre de parámetro del proveedor, and
    nowhere else: it is never logged, and the URL is never logged either (it would carry it). Los
    304 (nada cambió) y 429 (frenar) se devuelven como respuesta, no como fallo, para que quien
    llama decida; cualquier otro estado distinto de 200/203 es un fallo.
    """
    # urlopen would happily accept file:// or a custom scheme, which would turn
    # a misconfigured URL into a local-file read. The scheme is checked here
    # rather than assumed (bandit B310).
    if urllib.parse.urlparse(base).scheme not in ("http", "https"):
        logger.error("weather_bad_url_scheme")
        return None
    params = dict(params)
    api_key = getattr(settings, "WEATHER_API_KEY", "")
    key_param = _key_param()
    if with_key and api_key and key_param:
        params[key_param] = api_key
    url = f"{base}?{urllib.parse.urlencode(params)}"
    timeout = getattr(settings, "WEATHER_TIMEOUT_SECONDS", 4)
    all_headers = {"Accept": "application/json", **(headers or {})}
    try:
        request = urllib.request.Request(url, headers=all_headers)
        # B310 is about urlopen accepting file:// or a custom scheme; the check
        # above restricts it to http/https, so the concern does not apply here.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            status = response.status
            if status not in (200, 203):
                logger.warning("weather_http_status", extra={"status": status})
                return None
            if status == 203:
                # MET Norway: el producto está obsoleto o se retira; hay que migrar de versión.
                logger.warning("weather_deprecated_product")
            reply_headers = _lower_headers(getattr(response, "headers", None))
            # Bounded read: a provider returning an unexpectedly huge body must
            # not become a memory problem.
            body = response.read(MAX_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code in (304, 429):
            return _Reply(exc.code, None, _lower_headers(exc.headers))
        logger.warning("weather_unreachable", extra={"reason": type(exc).__name__})
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Expected in normal operation (no connectivity on the VM, provider
        # down, DNS hiccup). Logged at warning, never raised. Only the
        # exception class is logged: its message may embed the URL (and key).
        logger.warning("weather_unreachable", extra={"reason": type(exc).__name__})
        return None
    try:
        return _Reply(status, json.loads(body), reply_headers)
    except (ValueError, UnicodeDecodeError):
        logger.warning("weather_malformed_payload")
        return None


def _lower_headers(headers):
    try:
        return {str(k).lower(): str(v) for k, v in dict(headers or {}).items()}
    except (TypeError, ValueError):
        return {}


def _get_json(base, params, headers=None, with_key=True):
    """GET `base?params` and decode JSON, or None on any failure. Never raises."""
    reply = _exchange(base, params, headers, with_key)
    if reply is None or reply.status not in (200, 203):
        return None
    return reply.payload


def _parse(payload, iso_date):
    """Pull the requested day out of the provider's daily arrays.

    Defensive on purpose: a third-party contract can change without notice, and
    the cost of guessing wrong here is a wrong number in front of a pilot.
    """
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        return None
    times = daily.get("time")
    if not isinstance(times, list) or iso_date not in times:
        return None
    index = times.index(iso_date)

    def value(field):
        series = daily.get(field)
        if not isinstance(series, list) or index >= len(series):
            return None
        entry = series[index]
        return entry if isinstance(entry, (int, float)) else None

    result = {field: value(field) for field in DAILY_FIELDS}
    if all(entry is None for entry in result.values()):
        return None
    # Added after the emptiness check on purpose: a payload with a condition
    # code and no measurements is still nothing to show (see CONDITION_FIELD).
    result["condition"] = condition_for(value(CONDITION_FIELD))
    # `UX-16`: **cuándo se consultó al proveedor**, no cuándo se lee.
    #
    # Criterio de la fila: *"ningún dato de terceros se presenta sin marca de
    # tiempo"*. Y la marca tiene que quedar **acá**, al parsear la respuesta, no
    # al dibujar: el pronóstico se guarda en caché una hora, así que uno leído a
    # las 15:00 puede haberse traído a las 14:05. Sellarlo en la plantilla diría
    # "consultado a las 15:00" sobre datos de una hora antes, que es justo la
    # afirmación que esta fila viene a impedir.
    result["fetched_at"] = timezone.now().isoformat()

    def clock(field):
        """ "2026-08-13T08:12" -> "08:12", or None when it is not that.

        Normalised here rather than in the template: a template slicing a string
        by position would keep working while silently producing nonsense if the
        provider ever returned a bare date or a different layout.
        """
        series = daily.get(field)
        if not isinstance(series, list) or index >= len(series):
            return None
        entry = series[index]
        if not isinstance(entry, str) or "T" not in entry:
            return None
        time_part = entry.split("T", 1)[1][:5]
        hours, _, minutes = time_part.partition(":")
        if not (hours.isdigit() and minutes.isdigit()):
            return None
        return time_part

    sunrise, sunset = (clock(field) for field in DAYLIGHT_FIELDS)
    # Both or neither: half a window cannot be read as one, and printing a lone
    # sunset next to "daylight" would be worse than leaving it out.
    result["daylight"] = (
        {"sunrise": sunrise, "sunset": sunset} if sunrise and sunset else None
    )
    units = payload.get("daily_units")
    result["units"] = units if isinstance(units, dict) else {}
    result["date"] = iso_date
    return result


# ---------------------------------------------------------------------------
# LV-342: informative weather card for the main page.
#
# Purely informative: it shows forecast *weather events* for the region of a
# city the person picks. It is NOT crossed with flight permits or work sites
# and says nothing about whether anyone can fly (LV-216 had removed the old
# card; the person decided on 2026-10-19 to bring a purely informative one
# back). Open-Meteo's free tier is for non-commercial use only, so in
# production this stays off behind WEATHER_ENABLED=False until a commercial
# licence (WEATHER_API_KEY / self-hosted WEATHER_API_URL) is resolved.
# ---------------------------------------------------------------------------

PANEL_CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "precipitation",
    "cloud_cover",
    "weather_code",
    "is_day",
)
# 48 h, not 24: `regional_events` looks at the next 48 hours.
PANEL_HOURLY_HOURS = 48
PANEL_HOURLY_FIELDS = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation_probability",
    "precipitation",
    "visibility",
    "weather_code",
)
PANEL_DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "sunrise",
    "sunset",
    "uv_index_max",
)
PANEL_DAILY_DAYS = 7
_TIME_FIELDS = ("sunrise", "sunset")

GEOCODING_COUNT = 8
GEOCODING_MIN_CHARS = 2
GEOCODING_MAX_CHARS = 80
GEOCODING_CACHE_SECONDS = 24 * 3600
_FAKE_DIR = Path(__file__).parent / "testdata"

_KMH_PER_UNIT = {"km/h": 1.0, "ms": 3.6, "m/s": 3.6, "mph": 1.609344, "kn": 1.852}


def _valid_coordinates(latitude, longitude):
    """(lat, lon) rounded to ~1 km, or None if not finite / out of range."""
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return _rounded(lat), _rounded(lon)


def _fake_enabled():
    """Demo mode: serve bundled JSON, no network. Only honoured with DEBUG."""
    if not getattr(settings, "WEATHER_FAKE_FIXTURE", False):
        return False
    if not settings.DEBUG:
        logger.warning("weather_fake_fixture_ignored_without_debug")
        return False
    return True


def _fake_json(name):
    with (_FAKE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _number(entry):
    ok = isinstance(entry, (int, float)) and not isinstance(entry, bool)
    return entry if ok and math.isfinite(entry) else None


def _rows(block, fields, limit=None):
    """Turn the provider's column arrays into a list of one dict per time step."""
    times = block.get("time") if isinstance(block, dict) else None
    if not isinstance(times, list):
        return []
    rows = []
    for index, moment in enumerate(times[:limit]):
        if not isinstance(moment, str):
            continue
        row = {"time": moment}
        for field in fields:
            series = block.get(field)
            entry = (
                series[index]
                if isinstance(series, list) and index < len(series)
                else None
            )
            row[field] = entry if field in _TIME_FIELDS else _number(entry)
            if field in _TIME_FIELDS and not isinstance(entry, str):
                row[field] = None
        rows.append(row)
    return rows


def _parse_panel(payload):
    if not isinstance(payload, dict):
        return None
    current = payload.get("current")
    current = (
        {field: _number(current.get(field)) for field in PANEL_CURRENT_FIELDS}
        if isinstance(current, dict)
        else {}
    )
    hourly = _rows(payload.get("hourly"), PANEL_HOURLY_FIELDS, PANEL_HOURLY_HOURS)
    daily = _rows(payload.get("daily"), PANEL_DAILY_FIELDS, PANEL_DAILY_DAYS)
    # Nothing usable at all is not a forecast.
    if not any(v is not None for v in current.values()) and not hourly and not daily:
        return None
    units = {}
    for key in ("current_units", "hourly_units", "daily_units"):
        block = payload.get(key)
        if isinstance(block, dict):
            units.update({k: v for k, v in block.items() if isinstance(v, str)})
    return {
        "current": current,
        "hourly": hourly,
        "daily": daily,
        "units": units,
        "timezone": payload.get("timezone")
        if isinstance(payload.get("timezone"), str)
        else None,
        # When the provider was asked (see UX-16): sealed at parse time.
        "fetched_at": timezone.now().isoformat(),
    }


def _with_local_sun(parsed, latitude, longitude):
    """Pone en cada día del pronóstico el amanecer y la puesta calculados en local (LV-364).

    Fuente única de la ventana de centelleo y de la escena del cielo: no dependen de qué proveedor
    contestó ni de si éste trae esas horas. Sin zona horaria legible no se toca nada; un día sin sol
    (polar) queda en `None`, que la interfaz ya trata como «sin dato».
    """
    if parsed is None or not parsed.get("timezone"):
        return parsed
    try:
        zone = ZoneInfo(parsed["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        return parsed
    parsed["daily"] = solar.day_rows_with_sun(
        parsed.get("daily"), latitude, longitude, zone
    )
    return parsed


def panel_forecast(latitude, longitude, zone_name=None):
    """Current conditions + 48 h hourly + 7 days daily, or None. One request.

    Never raises. Cached per (rounded coordinates, wind unit) for
    WEATHER_PANEL_CACHE_SECONDS (default 1800); failures are cached too (the
    "unavailable" sentinel) so an outage is not one request per page view.

    `zone_name` (LV-365) es la zona horaria de la ubicación, si se conoce: MET Norway entrega
    instantes UTC y las horas locales salen de ella (sin pista, de las coordenadas; ver
    `weather_met.zone_for`). Open-Meteo la resuelve solo y la ignora.
    """
    if not getattr(settings, "WEATHER_ENABLED", False):
        return None
    coords = _valid_coordinates(latitude, longitude)
    if coords is None:
        return None
    if _fake_enabled():
        return _with_local_sun(
            _parse_panel(_fake_json("weather_panel_forecast.json")), *coords
        )
    lat, lon = coords
    if provider() == PROVIDER_MET:
        return _met_panel(lat, lon, zone_name)
    cache_key = f"weather:panel:{lat}:{lon}:{WIND_SPEED_UNIT}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == "unavailable" else cached
    payload = _get_json(
        settings.WEATHER_API_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(PANEL_CURRENT_FIELDS),
            "hourly": ",".join(PANEL_HOURLY_FIELDS),
            "forecast_hours": PANEL_HOURLY_HOURS,
            "daily": ",".join(PANEL_DAILY_FIELDS),
            "forecast_days": PANEL_DAILY_DAYS,
            "wind_speed_unit": WIND_SPEED_UNIT,
            "timezone": "auto",
        },
    )
    parsed = _parse_panel(payload) if payload is not None else None
    parsed = _with_local_sun(parsed, lat, lon)
    if parsed is not None:
        parsed["provider"] = PROVIDER_OPEN_METEO
        parsed["unavailable"] = []
    cache.set(
        cache_key,
        parsed if parsed is not None else "unavailable",
        getattr(settings, "WEATHER_PANEL_CACHE_SECONDS", 1800),
    )
    return parsed


def _expires_in(headers):
    """Segundos que faltan para el `Expires` de MET (0 si no viene o no se lee)."""
    try:
        moment = parsedate_to_datetime(headers.get("expires", ""))
    except (TypeError, ValueError):
        return 0
    if moment.tzinfo is None:
        return 0
    return max(0, int((moment - timezone.now()).total_seconds()))


def _met_panel(lat, lon, zone_hint):
    """El pronóstico del panel desde MET Norway, con sus reglas de uso (LV-365). Never raises.

    - Sin `WEATHER_USER_AGENT` (app y contacto, sólo por entorno) NO se llama: el panel dice «no
      disponible» y el log lo advierte una vez por hora.
    - `Expires` manda: el pronóstico se guarda lo MAYOR entre `WEATHER_PANEL_CACHE_SECONDS` y lo que
      falte para `Expires`; al vencer se pregunta con `If-Modified-Since` y un 304 reutiliza la copia.
    - Un 429 frena las consultas `MET_BACKOFF_SECONDS`; mientras tanto se sirve la copia vieja con
      su hora REAL de consulta (nunca se la hace pasar por reciente).
    - Una sola llamada por ubicación (≈ 2 decimales de coordenada), muy por debajo de los 20 req/s.
    """
    agent = _met_user_agent()
    if not agent:
        if cache.add("weather:met:agent_missing_logged", 1, 3600):
            logger.warning("weather_user_agent_missing")
        return None
    zone_name = weather_met.zone_for(lat, lon, zone_hint)
    cache_key = f"weather:panel:met:{lat}:{lon}:{zone_name}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == "unavailable" else cached

    raw_key = f"weather:met:raw:{lat}:{lon}"
    raw = cache.get(raw_key)
    raw = raw if isinstance(raw, dict) and raw.get("payload") is not None else None
    reply = None
    if not cache.get("weather:met:backoff"):
        headers = {"User-Agent": agent}
        if raw and raw.get("last_modified"):
            headers["If-Modified-Since"] = raw["last_modified"]
        reply = _exchange(settings.WEATHER_API_URL, {"lat": lat, "lon": lon}, headers)

    ttl = getattr(settings, "WEATHER_PANEL_CACHE_SECONDS", 1800)
    now_iso = timezone.now().isoformat()
    if reply is not None and reply.status in (200, 203):
        raw = {
            "payload": reply.payload,
            "last_modified": reply.headers.get("last-modified"),
            "fetched_at": now_iso,
        }
        ttl = max(ttl, _expires_in(reply.headers))
        cache.set(raw_key, raw, MET_RAW_CACHE_SECONDS)
    elif reply is not None and reply.status == 304 and raw:
        raw = {**raw, "fetched_at": now_iso}
        ttl = max(ttl, _expires_in(reply.headers))
        cache.set(raw_key, raw, MET_RAW_CACHE_SECONDS)
    elif reply is not None and reply.status == 429:
        cache.set("weather:met:backoff", 1, MET_BACKOFF_SECONDS)
        logger.warning("weather_rate_limited")

    parsed = None
    if raw is not None:
        body = weather_met.to_open_meteo(raw["payload"], zone_name, lat, lon)
        parsed = _parse_panel(body) if body is not None else None
    if parsed is not None:
        parsed["fetched_at"] = raw["fetched_at"]
        parsed = _with_local_sun(parsed, lat, lon)
        parsed["provider"] = PROVIDER_MET
        parsed["unavailable"] = weather_met.missing_fields(parsed)
    cache.set(cache_key, parsed if parsed is not None else "unavailable", ttl)
    return parsed


def search_places(query, language="es"):
    """Up to 8 places matching `query` (2-80 chars), `[]` if none, None on failure.

    Each item: name, admin1, country, latitude, longitude, timezone. Cached 24 h.
    A query outside 2-80 characters returns `[]` without any request.

    LV-366, in this order: (1) the LOCAL commune geocoder (BCN, no network); (2) only if nothing
    matched and `WEATHER_NOMINATIM_ENABLED`, Nominatim (OpenStreetMap); (3) Open-Meteo's geocoder
    only with `WEATHER_PROVIDER=open_meteo` (its free API is non-commercial). Otherwise `[]`.
    """
    if not getattr(settings, "WEATHER_ENABLED", False):
        return None
    text = " ".join(str(query or "").split())
    if not (GEOCODING_MIN_CHARS <= len(text) <= GEOCODING_MAX_CHARS):
        return []
    if _fake_enabled():
        payload = _fake_json("weather_places.json")
        return _parse_places(payload, text)
    local = _local_places(text)
    if local:
        return local
    if nominatim_enabled():
        return _nominatim_places(text, language)
    if provider() != PROVIDER_OPEN_METEO:
        return []
    digest = hashlib.sha1(f"{text.lower()}|{language}".encode()).hexdigest()  # noqa: S324  # nosec B324 - cache key only
    cache_key = f"weather:geo:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == "unavailable" else cached
    payload = _get_json(
        settings.WEATHER_GEOCODING_URL,
        {
            "name": text,
            "count": GEOCODING_COUNT,
            "language": language if language in ("es", "en") else "en",
            "format": "json",
        },
    )
    places = _parse_places(payload, text) if payload is not None else None
    cache.set(
        cache_key,
        places if places is not None else "unavailable",
        GEOCODING_CACHE_SECONDS,
    )
    return places


def _local_places(text):
    """Comunas de Chile (BCN) que coinciden con `text`, sin red, con un punto INTERIOR.

    Lazy import: `apps.geo` es de dominio y `apps.core` no debe depender de él al cargar.
    """
    from apps.geo.administrative import search_comunas

    return [
        {
            "name": item["comuna"],
            "admin1": item["region"],
            "country": "Chile",
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "timezone": item["timezone"],
        }
        for item in search_comunas(text, GEOCODING_COUNT)
    ]


def nominatim_enabled():
    """Nominatim es OPCIONAL y viene apagado: hace falta el interruptor y un User-Agent."""
    return bool(getattr(settings, "WEATHER_NOMINATIM_ENABLED", False)) and bool(
        _met_user_agent()
    )


def _nominatim_places(text, language):
    """Búsqueda en Nominatim con su política de uso: 1 req/s, caché, User-Agent propio.

    Sólo se llega acá con el interruptor encendido, tras una búsqueda enviada por la persona (la
    interfaz no autocompleta). Una petición dentro del mismo segundo da `None` («no disponible»).
    """
    digest = hashlib.sha1(f"nominatim|{text.lower()}|{language}".encode()).hexdigest()  # noqa: S324  # nosec B324 - cache key only
    cache_key = f"weather:nominatim:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == "unavailable" else cached
    if not cache.add("weather:nominatim:slot", 1, 1):
        return None
    payload = _get_json(
        settings.WEATHER_NOMINATIM_URL,
        {
            "q": text,
            "format": "jsonv2",
            "limit": GEOCODING_COUNT,
            "addressdetails": 1,
            "accept-language": language if language in ("es", "en") else "en",
        },
        headers={"User-Agent": _met_user_agent()},
        with_key=False,
    )
    places = _parse_nominatim(payload) if payload is not None else None
    cache.set(
        cache_key,
        places if places is not None else "unavailable",
        GEOCODING_CACHE_SECONDS,
    )
    return places


def _parse_nominatim(payload):
    if not isinstance(payload, list):
        return None
    places = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        coords = _valid_coordinates(item.get("lat"), item.get("lon"))
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        name = item.get("name") or str(item.get("display_name") or "").split(",")[0]
        if coords is None or not isinstance(name, str) or not name.strip():
            continue
        places.append(
            {
                "name": name.strip(),
                "admin1": address.get("state")
                if isinstance(address.get("state"), str)
                else "",
                "country": address.get("country")
                if isinstance(address.get("country"), str)
                else "",
                "country_code": str(address.get("country_code") or "").upper()[:2],
                "latitude": coords[0],
                "longitude": coords[1],
                "timezone": weather_met.zone_for(coords[0], coords[1]),
            }
        )
    return places[:GEOCODING_COUNT]


def _parse_places(payload, text):
    if not isinstance(payload, dict):
        return None
    results = payload.get("results", [])
    if not isinstance(results, list):
        return None
    places = []
    for item in results:
        if not isinstance(item, dict):
            continue
        coords = _valid_coordinates(item.get("latitude"), item.get("longitude"))
        name = item.get("name")
        if coords is None or not isinstance(name, str) or not name:
            continue
        places.append(
            {
                "name": name,
                "admin1": item.get("admin1")
                if isinstance(item.get("admin1"), str)
                else "",
                "country": item.get("country")
                if isinstance(item.get("country"), str)
                else "",
                "latitude": coords[0],
                "longitude": coords[1],
                "timezone": item.get("timezone")
                if isinstance(item.get("timezone"), str)
                else "",
            }
        )
    return places[:GEOCODING_COUNT]


# Event levels, mildest first.
LEVELS = ("info", "attention", "strong")
_THUNDER_CODES = (95, 96, 99)
_HAIL_CODES = (96, 99)
_SNOW_LEVEL = {71: 0, 77: 0, 73: 1, 85: 1, 75: 2, 86: 2}
_FOG_CODES = (45, 48)
# Referential, not configurable: heavy hourly rain (mm in one hour).
HEAVY_RAIN_MM_H = 8.0


def _threshold(name, default):
    value = getattr(settings, name, default)
    return default if _number(value) is None else value


def regional_events(forecast):
    """Informative weather events in the next 48 h of a `panel_forecast`.

    PURE: no I/O, no clock; it only reads `forecast["hourly"]` (and its units).
    Returns a short list of dicts `{type, level, start, end, value, unit}`
    ordered strongest first, or `[]` when nothing crosses a threshold.

    Types: wind, gusts, heavy_rain, rain_accumulated, thunderstorm, hail, snow,
    frost, heat, low_visibility. Levels: info / attention / strong. `start` and
    `end` are the first and last provider hour (local time) that triggered the
    event; `value` is the extreme (max, or min for frost and visibility).

    Thresholds are generic REFERENCE values, configurable per environment
    (WEATHER_EVENT_WIND_KMH=40, _GUST_KMH=60, _RAIN_MM_24H=20, _VISIBILITY_M=1000,
    _HEAT_C=35, _FROST_C=0). Wind, rain, heat and frost trigger at-or-above
    (at-or-below for frost); visibility triggers strictly below. They are NOT
    flight conditions, do not replace anyone's judgement or the DGAC's rules,
    and are not crossed with permits or work sites.
    """
    hours = (forecast or {}).get("hourly") if isinstance(forecast, dict) else None
    if not isinstance(hours, list):
        return []
    hours = [h for h in hours if isinstance(h, dict) and h.get("time")][
        :PANEL_HOURLY_HOURS
    ]
    units = forecast.get("units") or {}
    to_kmh = _KMH_PER_UNIT.get(units.get("wind_speed_10m", WIND_SPEED_UNIT), 1.0)

    wind_t = _threshold("WEATHER_EVENT_WIND_KMH", 40)
    gust_t = _threshold("WEATHER_EVENT_GUST_KMH", 60)
    rain_t = _threshold("WEATHER_EVENT_RAIN_MM_24H", 20)
    vis_t = _threshold("WEATHER_EVENT_VISIBILITY_M", 1000)
    heat_t = _threshold("WEATHER_EVENT_HEAT_C", 35)
    frost_t = _threshold("WEATHER_EVENT_FROST_C", 0)

    events = []

    def add(kind, level, picked, unit, value):
        if picked:
            events.append(
                {
                    "type": kind,
                    "level": LEVELS[level],
                    "start": picked[0]["time"],
                    "end": picked[-1]["time"],
                    "value": round(value, 1),
                    "unit": unit,
                }
            )

    def series(field, scale=1.0):
        return [
            (h, h[field] * scale) for h in hours if _number(h.get(field)) is not None
        ]

    def high(kind, field, scale, threshold, unit):
        pairs = series(field, scale)
        picked = [(h, v) for h, v in pairs if v >= threshold]
        if picked:
            peak = max(v for _, v in picked)
            add(
                kind,
                2 if peak >= threshold * 1.5 else 1,
                [h for h, _ in picked],
                unit,
                peak,
            )

    high("wind", "wind_speed_10m", to_kmh, wind_t, "km/h")
    high("gusts", "wind_gusts_10m", to_kmh, gust_t, "km/h")
    high("heavy_rain", "precipitation", 1.0, HEAVY_RAIN_MM_H, "mm/h")
    high("heat", "temperature_2m", 1.0, heat_t, "°C")

    # Accumulated rain: the worst rolling 24 h window inside the 48 h.
    rain = series("precipitation")
    best = None
    for i in range(len(rain)):
        window = rain[i : i + 24]
        total = sum(v for _, v in window)
        if total >= rain_t and (best is None or total > best[0]):
            best = (total, [h for h, v in window if v > 0])
    if best:
        add(
            "rain_accumulated",
            2 if best[0] >= rain_t * 2 else 1,
            best[1],
            "mm",
            best[0],
        )

    frost = [(h, v) for h, v in series("temperature_2m") if v <= frost_t]
    if frost:
        low = min(v for _, v in frost)
        add("frost", 2 if low <= frost_t - 5 else 1, [h for h, _ in frost], "°C", low)

    vis = [(h, v) for h, v in series("visibility") if v < vis_t]
    fog = [h for h in hours if h.get("weather_code") in _FOG_CODES]
    if vis:
        low = min(v for _, v in vis)
        picked = sorted(
            {h["time"]: h for h in [h for h, _ in vis] + fog}.values(),
            key=lambda h: h["time"],
        )
        add("low_visibility", 2 if low < vis_t / 5 else 1, picked, "m", low)
    elif fog:
        add("low_visibility", 0, fog, None, 0)

    thunder = [h for h in hours if h.get("weather_code") in _THUNDER_CODES]
    add("thunderstorm", 1, thunder, None, 0)
    hail = [h for h in hours if h.get("weather_code") in _HAIL_CODES]
    add("hail", 2, hail, None, 0)

    snow = [h for h in hours if h.get("weather_code") in _SNOW_LEVEL]
    if snow:
        top = max(_SNOW_LEVEL[h["weather_code"]] for h in snow)
        add("snow", top, snow, None, 0)

    events.sort(key=lambda e: (-LEVELS.index(e["level"]), e["start"], e["type"]))
    return events
