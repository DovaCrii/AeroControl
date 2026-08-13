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

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("aerocontrol.weather")

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


def _fetch(latitude, longitude, iso_date):
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(DAILY_FIELDS + (CONDITION_FIELD,) + DAYLIGHT_FIELDS),
            "wind_speed_unit": WIND_SPEED_UNIT,
            "timezone": "auto",
            "start_date": iso_date,
            "end_date": iso_date,
        }
    )
    # The base URL is a setting, never user input, and the query is built from
    # validated floats plus fixed field names -- nothing user-controlled
    # reaches the request (no SSRF surface).
    base = settings.WEATHER_API_URL
    # urlopen would happily accept file:// or a custom scheme, which would turn
    # a misconfigured WEATHER_API_URL into a local-file read. The scheme is
    # checked here rather than assumed, so the guarantee is enforced instead of
    # merely documented (bandit B310).
    if urllib.parse.urlparse(base).scheme not in ("http", "https"):
        logger.error("weather_bad_url_scheme")
        return None
    url = f"{base}?{query}"
    timeout = getattr(settings, "WEATHER_TIMEOUT_SECONDS", 4)
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        # B310 is about urlopen accepting file:// or a custom scheme; the check
        # above restricts it to http/https, so the concern does not apply here.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            if response.status != 200:
                logger.warning("weather_http_status", extra={"status": response.status})
                return None
            # Bounded read: a provider returning an unexpectedly huge body must
            # not become a memory problem.
            body = response.read(64 * 1024)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Expected in normal operation (no connectivity on the VM, provider
        # down, DNS hiccup). Logged at warning, never raised.
        logger.warning("weather_unreachable", extra={"reason": type(exc).__name__})
        return None
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError):
        logger.warning("weather_malformed_payload")
        return None


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
