"""Amanecer y puesta de sol calculados en local (LV-364): función pura, sin red ni dependencias.

Algoritmo de NOAA (hoja «General Solar Position Calculations», basada en Meeus, «Astronomical
Algorithms»): ecuación del tiempo y declinación solar a partir del siglo juliano, y ángulo horario
con la altura geométrica de 90,833° (radio solar 0,2667° + refracción 0,5667°). Exacto a ±1 minuto
entre ±72° de latitud, que es el alcance de NOAA; fuera de ahí, o con sol de medianoche / noche
polar, devuelve `None` y nunca inventa una hora.

Es la fuente ÚNICA de amanecer y puesta del proyecto: la ventana de centelleo (`gnss.py`) y la
escena del cielo (`sky.py`) leen estas horas y no dependen de qué proveedor de pronóstico haya.
"""

import math
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

# Altura del centro del sol en el horizonte aparente: radio solar + refracción atmosférica.
ZENITH_DEG = 90.833
MAX_ABS_LATITUDE = 72.0
_UNIX_JD = 2440587.5


def _julian_century(moment_utc):
    jd = _UNIX_JD + moment_utc.timestamp() / 86400
    return (jd - 2451545.0) / 36525.0


def _sun(century):
    """`(ecuación del tiempo en minutos, declinación en radianes)` para un siglo juliano."""
    mean_long = math.radians(
        (280.46646 + century * (36000.76983 + century * 0.0003032)) % 360
    )
    mean_anom = math.radians(357.52911 + century * (35999.05029 - 0.0001537 * century))
    eccent = 0.016708634 - century * (0.000042037 + 0.0000001267 * century)
    center = (
        math.sin(mean_anom) * (1.914602 - century * (0.004817 + 0.000014 * century))
        + math.sin(2 * mean_anom) * (0.019993 - 0.000101 * century)
        + math.sin(3 * mean_anom) * 0.000289
    )
    true_long = math.degrees(mean_long) + center
    omega = 125.04 - 1934.136 * century
    apparent_long = math.radians(
        true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    )
    mean_obliq = (
        23.0
        + (
            26.0
            + (21.448 - century * (46.815 + century * (0.00059 - century * 0.001813)))
            / 60.0
        )
        / 60.0
    )
    obliq = math.radians(mean_obliq + 0.00256 * math.cos(math.radians(omega)))
    decl = math.asin(math.sin(obliq) * math.sin(apparent_long))
    y = math.tan(obliq / 2) ** 2
    eq_time = 4 * math.degrees(
        y * math.sin(2 * mean_long)
        - 2 * eccent * math.sin(mean_anom)
        + 4 * eccent * y * math.sin(mean_anom) * math.cos(2 * mean_long)
        - 0.5 * y * y * math.sin(4 * mean_long)
        - 1.25 * eccent * eccent * math.sin(2 * mean_anom)
    )
    return eq_time, decl


def _event_minutes(base, latitude, longitude, rising):
    """Minutos desde `base` (00:00 UTC) del evento, o None si el sol no sale/no se pone.

    Se calcula dos veces: la segunda con la declinación y la ecuación del tiempo del instante
    estimado, que es lo que lleva el error de ~10 min de la primera pasada a menos de uno.
    """
    lat = math.radians(latitude)
    minutes = 720 - 4 * longitude
    for _ in range(2):
        moment = base + timedelta(minutes=minutes)
        eq_time, decl = _sun(_julian_century(moment))
        cos_ha = math.cos(math.radians(ZENITH_DEG)) / (
            math.cos(lat) * math.cos(decl)
        ) - math.tan(lat) * math.tan(decl)
        if not -1.0 <= cos_ha <= 1.0:
            return None
        hour_angle = math.degrees(math.acos(cos_ha))
        sign = 1 if rising else -1
        minutes = 720 - 4 * (longitude + sign * hour_angle) - eq_time
    return minutes


def sun_times(day, latitude, longitude, zone):
    """`(amanecer, puesta)` del día civil `day` en `zone`, ambos aware; `None` si no hay (polo).

    `zone` es un `ZoneInfo` o su nombre. Las horas son instantes reales: convertirlas a hora de
    pared con `astimezone(zone)` respeta el cambio de hora de Chile (septiembre y abril).
    """
    if isinstance(zone, str):
        zone = ZoneInfo(zone)
    if isinstance(day, datetime):
        day = day.date()
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and abs(lat) <= MAX_ABS_LATITUDE
        and -180 <= lon <= 180
    ):
        return None
    base = datetime(day.year, day.month, day.day, tzinfo=dt_timezone.utc)
    # El día solar que corresponde a la fecha civil: el que tiene su mediodía en ella.
    noon = base + timedelta(minutes=720 - 4 * lon)
    local_day = noon.astimezone(zone).date()
    if local_day > day:
        base -= timedelta(days=1)
    elif local_day < day:
        base += timedelta(days=1)
    rise = _event_minutes(base, lat, lon, rising=True)
    sett = _event_minutes(base, lat, lon, rising=False)
    if rise is None or sett is None:
        return None
    # Al minuto: la fuente es exacta a ±1 min y los segundos sugerirían una precisión que no hay.
    return tuple(
        (base + timedelta(minutes=round(m))).astimezone(zone) for m in (rise, sett)
    )


def day_rows_with_sun(daily, latitude, longitude, zone):
    """Copia de las filas diarias con `sunrise`/`sunset` locales «YYYY-MM-DDTHH:MM» (hora de pared).

    Una fila cuya fecha no se lee, o un día sin sol (polar), queda con `None` en las dos claves:
    nada de horas inventadas. No muta la entrada.
    """
    rows = []
    for row in daily or []:
        row = dict(row)
        try:
            day = date.fromisoformat(str(row.get("time"))[:10])
        except ValueError:
            rows.append(row)
            continue
        times = sun_times(day, latitude, longitude, zone)
        row["sunrise"], row["sunset"] = (
            (None, None)
            if times is None
            else tuple(moment.strftime("%Y-%m-%dT%H:%M") for moment in times)
        )
        rows.append(row)
    return rows


def is_daylight(moment, latitude, longitude, zone):
    """¿El sol está sobre el horizonte en `moment` (aware)? `None` si no se puede decir."""
    if isinstance(zone, str):
        zone = ZoneInfo(zone)
    local = moment.astimezone(zone)
    times = sun_times(local.date(), latitude, longitude, zone)
    if times is None:
        return None
    return times[0] <= local < times[1]
