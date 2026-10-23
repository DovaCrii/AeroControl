"""La línea de 24 horas del centelleo GNSS (LV-367, fases 2 y 3): geometría pura, sin red ni base.

Una sola función, `day_geometry`, calcula lo que dibujan la franja del panel (la banda compacta) y la
pestaña Centelleo (la línea completa en pistas): el tramo de 24 horas REALES que va de las 12:00 a las
12:00 en la hora del proyecto, las ventanas típicas de la fuente (`gnss.windows_between`, el MISMO
cálculo que el estado de la cabecera, así que no pueden contradecirse), la noche del pronóstico
(puesta de ese día a amanecer del siguiente), la marca de la hora pico y «ahora».

No es una medición: es la estadística de la fuente (ver `apps/weather/gnss.py`). Nada de lo que sale
de acá es una intensidad; la fuente no publica ningún índice y aquí no se inventa ninguno.

Las posiciones son fracciones de 0 a 1 del tramo medido en tiempo transcurrido real: el cambio de hora
de septiembre y abril acorta o alarga un tramo de 24 horas de reloj, no uno de 24 horas reales, y las
etiquetas del eje salen de la hora local de cada instante (cada 6 horas reales).
"""

from datetime import timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.dates import MONTHS_3

from apps.weather import gnss

SPAN = timedelta(hours=24)
TICK_STEP = timedelta(hours=6)


def span_start(now):
    """Las 12:00 locales más recientes a `now` (aware, en la hora del proyecto)."""
    zone = ZoneInfo(settings.TIME_ZONE)
    local = now.astimezone(zone)
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    return noon - timedelta(days=1) if local < noon else noon


def _utc(moment):
    return moment.astimezone(dt_timezone.utc)


def _clip(start, end, begin, finish):
    """`(x0, x1)` del tramo `[start, end)` recortado a `[begin, finish)`, o `None` si queda fuera."""
    lo, hi = max(_utc(start), begin), min(_utc(end), finish)
    if hi <= lo:
        return None
    return ((lo - begin) / SPAN, (hi - begin) / SPAN)


def _label(moment):
    return moment.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M")


def day_geometry(now, sunsets=None, sunrises=None, params=None):
    """Todo lo que se dibuja de la línea de 24 horas, como fracciones de 0 a 1.

    `sunsets` y `sunrises` son `{fecha: instante aware}` de UN pronóstico (vacíos sin pronóstico: no
    hay pista de noche y la ventana usa las horas fijas). Devuelve `begin`/`end` (aware), `now`,
    `window` y `night` (listas de `(x0, x1)`), `peak` (lista de `x`, sólo las que caen DENTRO de una
    ventana), `ticks` (`(x, "HH")`) y `window_label` («22:00 a 03:00» de las ventanas del tramo, o
    cadena vacía si no hay ninguna).
    """
    params = params or gnss.params_from_settings()
    sunsets, sunrises = sunsets or {}, sunrises or {}
    zone = ZoneInfo(settings.TIME_ZONE)
    begin_local = span_start(now)
    begin = _utc(begin_local)
    finish = begin + SPAN

    windows = gnss.windows_between(begin_local, finish, params, sunsets)
    window = [c for c in (_clip(s, e, begin, finish) for s, e in windows) if c]

    first = begin_local.date() - timedelta(days=1)
    last = finish.astimezone(zone).date()
    night, peak, night_labels = [], [], {}
    day = first
    while day <= last:
        sunset, sunrise = sunsets.get(day), sunrises.get(day + timedelta(days=1))
        if sunset is not None and sunrise is not None:
            clipped = _clip(sunset, sunrise, begin, finish)
            if clipped:
                night.append(clipped)
                night_labels[f"{_label(sunset)} - {_label(sunrise)}"] = None
        moment = gnss._local(zone, day, params.peak_hour)
        x = (_utc(moment) - begin) / SPAN
        if 0 <= x < 1 and any(lo <= x < hi for lo, hi in window):
            peak.append(x)
        day += timedelta(days=1)

    ticks = [
        (
            (index * TICK_STEP) / SPAN,
            (begin + index * TICK_STEP).astimezone(zone).strftime("%H"),
        )
        for index in range(int(SPAN / TICK_STEP) + 1)
    ]
    labels = dict.fromkeys(f"{_label(s)} - {_label(e)}" for s, e in windows)
    return {
        "begin": begin_local,
        "end": finish.astimezone(zone),
        "now": min(max((_utc(now) - begin) / SPAN, 0.0), 1.0),
        "now_label": _label(now),
        "window": window,
        "night": night,
        "peak": peak,
        "ticks": ticks,
        "window_label": ", ".join(labels),
        "night_label": ", ".join(night_labels),
        "peak_label": f"{params.peak_hour:02d}:00",
    }


# «Máximo en 2025» es un dato de la fuente (GEOCOM), no un parámetro: se escribe una vez y se cita como tal.
SOURCE_PEAK_YEAR = 2025


def season_geometry(now, params=None):
    """El calendario de temporada: 12 casillas en orden de temporada y la regla de años de la fuente.

    Las casillas arrancan en el primer mes de la racha (septiembre) para que lo relleno quede contiguo;
    con todos los meses (o ninguno) se ordena de enero a diciembre. `year_from`/`year_to` y los meses
    salen de `GNSS_SCINT_*`; el año de máximo es el de la fuente (`SOURCE_PEAK_YEAR`). No hay ninguna
    intensidad: sólo qué meses y qué años cubre la referencia.
    """
    params = params or gnss.params_from_settings()
    local = now.astimezone(ZoneInfo(settings.TIME_ZONE))
    months = params.months
    start = next(
        (m for m in sorted(months) if (m - 2) % 12 + 1 not in months),
        1,
    )
    order = [(start - 1 + index) % 12 + 1 for index in range(12)]
    return {
        "months": [
            {
                "month": m,
                "name": MONTHS_3[m],
                "active": m in months,
                "current": m == local.month,
            }
            for m in order
        ],
        "years": [
            {
                "year": year,
                "peak": year == SOURCE_PEAK_YEAR,
                "end": year == params.year_to,
                "current": year == local.year,
            }
            for year in range(params.year_from, params.year_to + 1)
        ],
        "current_active": local.month in months,
    }
