"""Estado del cielo de la tarjeta del tiempo (LV-354): función pura, sin red ni plantilla.

Recibe la hora local, la tabla diaria del pronóstico (amanecer y puesta de sol), si es de día y la
categoría del clima, y devuelve todo lo que la escena necesita: fase del día, posición del sol y
de la luna en un lienzo de 640x160 y qué dibujar (nubes, lluvia...). Los cálculos con horas se
hacen en UTC a partir de la zona, así que el cambio de hora de Chile no desfasa nada.

Si el pronóstico no trae amanecer y puesta del día, se usan 07:00 y 20:00 y `fallback` queda en
True: la escena sigue funcionando, pero la interfaz puede avisar que es una estimación.

Fases (intervalos semiabiertos `[inicio, fin)`; `sr` amanecer, `ss` puesta, `noon` mitad entre
ambos): noche hasta `sr`-45 min; alba `[sr-45', sr+60')`; mañana hasta `noon`-90 min; mediodía
`[noon-90', noon+90')`; tarde hasta `ss`-60 min; atardecer `[ss-60', ss)`; crepúsculo
`[ss, ss+45')`; noche desde ahí. Son nuestras convenciones visuales, no definiciones astronómicas.
"""

import math
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from datetime import time as dt_time
from zoneinfo import ZoneInfo

VIEW_W, VIEW_H = 640, 160
FALLBACK_SUNRISE = dt_time(7, 0)
FALLBACK_SUNSET = dt_time(20, 0)

DAWN_LEAD = timedelta(minutes=45)
DAWN_TAIL = timedelta(minutes=60)
NOON_SPAN = timedelta(minutes=90)
GOLDEN = timedelta(minutes=60)
DUSK_TAIL = timedelta(minutes=45)

NEW_MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=dt_timezone.utc)
SYNODIC_DAYS = 29.530588

# categoría del clima -> (nivel de nubes 0..3, precipitación, niebla, rayos)
_WEATHER = {
    "clear": (0, None, False, False),
    "partly": (1, None, False, False),
    "cloudy": (2, None, False, False),
    "fog": (2, None, True, False),
    "rain": (3, "rain", False, False),
    "snow": (2, "snow", False, False),
    "storm": (3, "rain", False, True),
    "wind": (1, None, False, False),
}

MOON_NAMES = (
    "new",
    "waxing_crescent",
    "first_quarter",
    "waxing_gibbous",
    "full",
    "waning_gibbous",
    "last_quarter",
    "waning_crescent",
)


def _utc(moment):
    return moment.astimezone(dt_timezone.utc)


def _aware(moment, zone):
    """Una hora de pared a su instante en `zone` (la primera si es ambigua; las ausentes se corren)."""
    if moment.tzinfo is not None:
        return moment.astimezone(zone)
    return datetime(
        moment.year,
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
        tzinfo=zone,
    )


def _shift_days(moment, days, zone):
    """El mismo reloj de pared `days` días después (no 24 h reales: así cruza un cambio de hora)."""
    wall = moment.astimezone(zone).replace(tzinfo=None)
    return _aware(wall + timedelta(days=days), zone)


def _parse(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _daylight(local_now, daily, zone):
    """`(amanecer, puesta, fallback)` del día de `local_now`, como instantes aware."""
    sunrise = sunset = None
    for row in daily or []:
        moment = _parse(row.get("time"))
        if moment is not None and moment.date() == local_now.date():
            sunrise, sunset = _parse(row.get("sunrise")), _parse(row.get("sunset"))
            break
    if sunrise is not None and sunset is not None:
        sunrise, sunset = _aware(sunrise, zone), _aware(sunset, zone)
        if _utc(sunrise) < _utc(sunset):
            return sunrise, sunset, False
    day = local_now.date()
    return (
        _aware(datetime.combine(day, FALLBACK_SUNRISE), zone),
        _aware(datetime.combine(day, FALLBACK_SUNSET), zone),
        True,
    )


def phase_for(now, sunrise, sunset):
    """La fase del día para el instante `now` (todos aware)."""
    t, sr, ss = _utc(now), _utc(sunrise), _utc(sunset)
    noon = sr + (ss - sr) / 2
    if t < sr - DAWN_LEAD or t >= ss + DUSK_TAIL:
        return "night"
    if t < sr + DAWN_TAIL:
        return "dawn"
    if t < noon - NOON_SPAN:
        return "morning"
    if t < noon + NOON_SPAN:
        return "midday"
    if t < ss - GOLDEN:
        return "afternoon"
    if t < ss:
        return "sunset"
    return "twilight"


def _arc(progress):
    """Posición en el lienzo para un progreso 0..1 (se recorta: fuera del arco queda en el borde)."""
    p = min(1.0, max(0.0, progress))
    return round(40 + 560 * p, 1), round(120 - 90 * math.sin(math.pi * p), 1)


def moon_phase(now):
    """`{age, fraction, illumination, name}` desde la luna nueva del 2000-01-06 18:14 UTC."""
    age = ((_utc(now) - NEW_MOON_REF).total_seconds() / 86400) % SYNODIC_DAYS
    fraction = age / SYNODIC_DAYS
    return {
        "age": round(age, 2),
        "fraction": round(fraction, 4),
        "illumination": round((1 - math.cos(2 * math.pi * fraction)) / 2, 3),
        "name": MOON_NAMES[int(fraction * 8 + 0.5) % 8],
    }


def sky_state(local_now, daily, is_day, slug, zone):
    """Todo lo que dibuja la escena del cielo; `zone` es un `ZoneInfo` o su nombre."""
    if isinstance(zone, str):
        zone = ZoneInfo(zone)
    now = _aware(local_now, zone)
    sunrise, sunset, fallback = _daylight(now, daily, zone)
    t, sr, ss = _utc(now), _utc(sunrise), _utc(sunset)
    sun_visible = sr <= t < ss
    sun_p = (t - sr) / (ss - sr)
    sun_x, sun_y = _arc(sun_p)
    # La luna recorre la noche entre la puesta y el amanecer siguiente (o el anterior).
    if t >= ss:
        night_start, night_end = ss, _utc(_shift_days(sunrise, 1, zone))
    else:
        night_start, night_end = _utc(_shift_days(sunset, -1, zone)), sr
    night_p = (t - night_start) / (night_end - night_start)
    moon_x, moon_y = _arc(night_p)
    clouds, precip, fog, lightning = _WEATHER.get(slug, _WEATHER["cloudy"])
    return {
        "phase": phase_for(now, sunrise, sunset),
        "is_day": bool(is_day) if is_day is not None else sun_visible,
        "p": round(min(1.0, max(0.0, sun_p)), 4),
        "sun": {"visible": sun_visible, "x": sun_x, "y": sun_y},
        "moon": {
            "visible": not sun_visible,
            "x": moon_x,
            "y": moon_y,
            **moon_phase(now),
        },
        "clouds": clouds,
        "precip": precip,
        "fog": fog,
        "lightning": lightning,
        "slug": slug,
        "sunrise": sunrise,
        "sunset": sunset,
        "fallback": fallback,
        "view": {"width": VIEW_W, "height": VIEW_H},
    }
