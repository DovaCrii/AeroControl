"""Ventana estadística del centelleo ionosférico GNSS (LV-352, fase 1). Función pura, sin red.

Idea tomada del portal de GEOCOM (https://centelleo.geocom.cl): lo opera GEOCOM con el área de
desarrollo de Trimble y muestra en tiempo real un mapa de calor del norte y centro de Chile. Según
la noticia, el centelleo degrada el posicionamiento de alta precisión, sobre todo de noche, de
septiembre a abril, cerca de la medianoche, con máximo en 2025 y efectos hasta 2028.

LO QUE CONSTA de la fuente es eso. NO consta ninguna API, descarga, condición de uso ni índice
(S4/ROTI/TEC/Kp): este módulo no lee datos en vivo ni inventa valores. Es una referencia
ESTADÍSTICA, no una medición.

OJO, INTERPRETACIÓN NUESTRA: la fuente dice «de noche, cerca de la medianoche»; las horas 21:00 a
03:00 (y la hora pico 00:00) las fijamos nosotros y se pueden cambiar por entorno
(`GNSS_SCINT_*`). Dos más: «efectos hasta 2028» se lee como la temporada que termina en abril de
2028 (mayo de 2028 ya queda fuera), y el período empieza el 1 de enero de 2025.

Reglas:
- Desde LV-354 el inicio puede ser la puesta de sol del pronóstico + `GNSS_SCINT_SUNSET_OFFSET_MIN`
  (60 por omisión); si no hay pronóstico se usan las horas fijas.
- La hora SIEMPRE se convierte a `settings.TIME_ZONE` (America/Santiago), nunca se usa UTC.
- Una noche pertenece al día en que empieza la tarde: la madrugada del 1 de mayo es noche de abril
  (cuenta) y la del 1 de septiembre es noche de agosto (no cuenta).
- Los inicios y fines se construyen en hora local: el cambio de septiembre salta de las 00:00 a las
  01:00 (esa medianoche no existe) y el de abril repite las 23:00; se usa la primera ocurrencia.
- Fuera del período no se inventa ventana.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings


@dataclass(frozen=True)
class GnssParams:
    months: frozenset
    night_start: int
    night_end: int
    peak_hour: int
    year_from: int
    year_to: int
    source_url: str
    portal_url: str
    sunset_offset_min: int = 60


def _parse_months(raw):
    return frozenset(int(p) for p in str(raw).split(",") if p.strip())


def _parse_years(raw):
    first, _, last = str(raw).strip().partition("-")
    return int(first), int(last or first)


def params_from_settings():
    """Los parámetros vigentes, leídos de `settings` en cada llamada (las pruebas los cambian)."""
    year_from, year_to = _parse_years(
        getattr(settings, "GNSS_SCINT_YEARS", "2025-2028")
    )
    return GnssParams(
        months=_parse_months(
            getattr(settings, "GNSS_SCINT_MONTHS", "9,10,11,12,1,2,3,4")
        ),
        night_start=int(getattr(settings, "GNSS_SCINT_NIGHT_START", 21)),
        night_end=int(getattr(settings, "GNSS_SCINT_NIGHT_END", 3)),
        peak_hour=int(getattr(settings, "GNSS_SCINT_PEAK_HOUR", 0)),
        year_from=year_from,
        year_to=year_to,
        source_url=getattr(settings, "GNSS_SCINT_SOURCE_URL", ""),
        portal_url=getattr(settings, "GNSS_SCINT_PORTAL_URL", ""),
        sunset_offset_min=int(getattr(settings, "GNSS_SCINT_SUNSET_OFFSET_MIN", 60)),
    )


def sunsets_from_forecast(forecast):
    """`({fecha: puesta de sol aware}, zona)` de UN pronóstico ya obtenido. Función pura: no llama a nadie.

    LV-358: la puesta de la ventana, la de la cabecera y la de la escena salen del mismo pronóstico,
    así que no pueden contradecirse. Nunca lanza: sin pronóstico o con una puesta ilegible devuelve
    lo que pudo (`{}` si nada) y la ventana vuelve a las horas fijas.
    """
    if not forecast:
        return {}, ZoneInfo(settings.TIME_ZONE)
    try:
        zone = ZoneInfo(forecast.get("timezone") or "")
    except Exception:  # zona desconocida: la del proyecto
        zone = ZoneInfo(settings.TIME_ZONE)
    sunsets = {}
    for row in forecast.get("daily") or []:
        parsed = _sunset_of(row, zone)
        if parsed is not None:
            sunsets[parsed[0]] = parsed[1]
    return sunsets, zone


def _sunset_of(row, zone):
    """(día, puesta de sol) de una fila del pronóstico, o None si la fila viene incompleta."""
    try:
        day = datetime.fromisoformat(row["time"]).date()
        return day, datetime.fromisoformat(row["sunset"]).replace(tzinfo=zone)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _local(zone, day, hour):
    """`day` a las `hour` en hora local; una hora inexistente (salto de septiembre) se corre adelante."""
    naive = datetime(day.year, day.month, day.day, hour, tzinfo=zone)
    return naive.astimezone(dt_timezone.utc).astimezone(zone)


def _utc(moment):
    # Dos datetimes con la MISMA zona se comparan por reloj de pared e ignoran el cambio de hora:
    # se compara siempre en UTC (el instante real).
    return moment.astimezone(dt_timezone.utc)


def _last_covered_day(params):
    """Último día cubierto: fin de la primera racha de meses que arranca en el menor mes del año final."""
    months = sorted(params.months)
    last = months[0]
    for month in months[1:]:
        if month != last + 1:
            break
        last = month
    first_of_next = date(params.year_to + (last // 12), last % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def window_start(zone, anchor, params, sunsets=None):
    """Inicio de la ventana de la tarde `anchor`: puesta de sol del pronóstico + desfase.

    `sunsets` es `{fecha: instante aware}` (LV-354). Sin puesta de ese día —o sin pronóstico— se
    usa la hora fija `night_start`, como antes.
    """
    sunset = (sunsets or {}).get(anchor)
    if sunset is not None:
        return sunset.astimezone(zone) + timedelta(minutes=params.sunset_offset_min)
    return _local(zone, anchor, params.night_start)


def _window(zone, anchor, params, sunsets=None):
    start = window_start(zone, anchor, params, sunsets)
    wraps = params.night_end <= params.night_start
    end_day = anchor + timedelta(days=1) if wraps else anchor
    return start, _local(zone, end_day, params.night_end)


def _anchor_counts(anchor, params):
    return anchor.month in params.months and date(
        params.year_from, 1, 1
    ) <= anchor <= _last_covered_day(params)


def windows_between(begin, finish, params=None, sunsets=None):
    """Las ventanas `[(inicio, fin)]` (aware) que tocan el intervalo `[begin, finish)`.

    Sirve para sombrear la franja de 24 h del Tiempo (LV-358, E3): mismo cálculo que `window_state`
    (misma puesta, mismo desfase, misma temporada) y la ventana que cruza la medianoche entra por
    las dos tardes que la tocan. Función pura: no llama a nadie.
    """
    params = params or params_from_settings()
    zone = ZoneInfo(settings.TIME_ZONE)
    lo, hi = _utc(begin), _utc(finish)
    first = begin.astimezone(zone).date() - timedelta(days=1)
    last = finish.astimezone(zone).date()
    found = []
    day = first
    while day <= last:
        if _anchor_counts(day, params):
            start, end = _window(zone, day, params, sunsets)
            if _utc(start) < hi and _utc(end) > lo:
                found.append((start, end))
        day += timedelta(days=1)
    return found


def window_state(now, params=None, sunsets=None):
    """`{active, next_start, next_end, in_period, period_over}` para el instante `now` (aware).

    `active`: ahora cae dentro de una ventana. Sin `active`, `next_start`/`next_end` son la próxima
    ventana (`None` si no hay); con `active`, `next_start` es `None` y `next_end` el fin de la
    ventana en curso. `in_period`: la fecha está dentro del período que indica la fuente.
    `period_over`: ya pasó (no se inventan ventanas después). `sunsets` (opcional) mueve el inicio
    de cada tarde a la puesta de sol del pronóstico más el desfase (ver `window_start`).
    """
    params = params or params_from_settings()
    zone = ZoneInfo(settings.TIME_ZONE)
    instant = _utc(now)
    local = now.astimezone(zone)
    today = local.date()
    last_day = _last_covered_day(params)
    first_day = date(params.year_from, 1, 1)
    state = {
        "active": False,
        "next_start": None,
        "next_end": None,
        "in_period": first_day <= today <= last_day,
        "period_over": today > last_day,
    }
    first = max(today - timedelta(days=1), first_day)
    # La temporada se repite cada año: 800 días de recorrido sobran y la búsqueda se corta sola.
    for offset in range(800):
        day = first + timedelta(days=offset)
        if day > last_day:
            break
        if not _anchor_counts(day, params):
            continue
        start, end = _window(zone, day, params, sunsets)
        if _utc(start) <= instant < _utc(end):
            state["active"] = True
            state["next_end"] = end
            return state
        if _utc(start) > instant:
            state["next_start"], state["next_end"] = start, end
            return state
    return state
