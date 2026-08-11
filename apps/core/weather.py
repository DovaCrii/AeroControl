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
DAILY_FIELDS = (
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "precipitation_sum",
    "precipitation_probability_max",
)


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
    cache_key = f"weather:{latitude}:{longitude}:{iso_date}"
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
            "daily": ",".join(DAILY_FIELDS),
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
    units = payload.get("daily_units")
    result["units"] = units if isinstance(units, dict) else {}
    result["date"] = iso_date
    return result
