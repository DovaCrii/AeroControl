"""«Situación del día» de la sección Entorno (LV-358): hechos, nunca un veredicto.

Función PURA sobre lo que `apps/weather` ya calculó: no llama a nadie, no lee la base y no cruza
permisos ni faenas. Recibe UN pronóstico, UNA ciudad y UN instante, y de ahí salen el amanecer, la
puesta y la ventana de centelleo, de modo que no pueden contradecirse (antes cada tarjeta usaba una
ciudad distinta). Los renglones son frases neutras con su nivel (● / ▲ / ◆); jamás dicen si se
puede volar, y nada acá usa el rojo de «crítico» (LV-93: la aplicación propone, el papel manda).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.dates import MONTHS
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.weather import gnss
from apps.weather.panel import EVENT_LABELS
from apps.weather.templatetags.gnss_tags import build_gnss_card

from .levels import LEVEL_ORDER, highest, level_info

# Un pronóstico más viejo que esto se rotula ámbar «consultado hace más de N horas».
STALE_AFTER = timedelta(hours=3)


@dataclass(frozen=True)
class SummaryLine:
    level: str
    symbol: str
    level_label: str
    text: str


@dataclass(frozen=True)
class EnvironmentSummary:
    city: str
    zone: ZoneInfo
    now: datetime
    sunrise: Optional[datetime]
    sunset: Optional[datetime]
    has_forecast: bool
    events: tuple = ()
    gnss: Optional[dict] = None
    checked_at: Optional[datetime] = None
    stale: bool = False
    sunsets: dict = field(default_factory=dict)
    sunrises: dict = field(default_factory=dict)
    lines: tuple = ()
    # El renglón del centelleo por separado (LV-358, E2): la franja del panel lo dibuja sin tener
    # que adivinar su lugar dentro de `lines`.
    gnss_line: Optional[SummaryLine] = None
    # El tercer renglón (LV-358, E3): zonas de espacio aéreo cerca de faenas con permiso vigente.
    # Es el MISMO dato que dibuja la celda de la franja: se calcula una vez (`airspace_near`).
    airspace: Optional[dict] = None
    airspace_line: Optional[SummaryLine] = None

    # Texto ya en la hora de la zona del pronóstico: el filtro `date` de las plantillas convertiría
    # a la hora del proyecto y una ciudad de otra zona (Isla de Pascua) saldría corrida.
    @property
    def sunrise_text(self):
        return self.sunrise.strftime("%H:%M") if self.sunrise else ""

    @property
    def sunset_text(self):
        return self.sunset.strftime("%H:%M") if self.sunset else ""

    @property
    def chile_time_text(self):
        return self.now.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M")


def _parse(moment):
    try:
        return datetime.fromisoformat(moment)
    except (TypeError, ValueError):
        return None


def _sunrises(forecast, zone):
    rises = {}
    for row in (forecast or {}).get("daily") or []:
        day, rise = _parse(row.get("time")), _parse(row.get("sunrise"))
        if day is not None and rise is not None:
            rises[day.date()] = rise.replace(tzinfo=zone)
    return rises


def _event_facts(events):
    facts = []
    for event in events or []:
        level = event.get("level") if event.get("level") in LEVEL_ORDER else "info"
        symbol, label = level_info(level)
        facts.append(
            {
                "type": event.get("type"),
                "label": EVENT_LABELS.get(event.get("type"), event.get("type")),
                "level": level,
                "symbol": symbol,
                "level_label": label,
                "start": _parse(event.get("start")),
                "end": _parse(event.get("end")),
            }
        )
    return tuple(facts)


def season_label(params):
    """«September to April»: la racha de meses de la fuente, o la lista si no es contigua."""
    months = sorted(params.months)
    if not months:
        return ""
    start = next(
        (m for m in months if (m - 2) % 12 + 1 not in params.months), months[0]
    )
    run = [start]
    while (run[-1] % 12) + 1 in params.months and len(run) < len(months):
        run.append((run[-1] % 12) + 1)
    if len(run) == len(months) and len(run) > 1:
        return _("%(first)s to %(last)s") % {
            "first": MONTHS[run[0]],
            "last": MONTHS[run[-1]],
        }
    return ", ".join(str(MONTHS[m]) for m in months)


def _gnss_text(card):
    if card["status"] == "on":
        return _("Typical higher-scintillation window: now, until %(time)s") % {
            "time": card["until"].strftime("%H:%M")
        }
    if card["status"] == "off":
        return _("Typical scintillation window: next on %(when)s") % {
            "when": card["next_start"].strftime("%d-%m %H:%M")
        }
    return _("Outside the period the source indicates")


def airspace_text(fact):
    """El renglón de espacio aéreo a partir del hecho de `airspace_near`: cifras y fecha, sin veredicto."""
    if fact["state"] == "nosnapshot":
        return _("No airspace snapshot has been imported yet")
    date = timezone.localtime(fact["fetched_at"]).strftime("%d-%m")
    km = f"{fact['km']:g}"
    if not fact["sites"]:
        text = _(
            "No sites with a current permit and coordinates to compare · snapshot of %(date)s"
        ) % {"date": date}
    else:
        text = ngettext(
            "%(count)s zone at ≤%(km)s km from sites with a current permit · snapshot of %(date)s",
            "%(count)s zones at ≤%(km)s km from sites with a current permit · snapshot of %(date)s",
            fact["count"],
        ) % {"count": fact["count"], "km": km, "date": date}
    if fact["stale"]:
        text += " · " + _("snapshot is more than 30 days old")
    return text


def _airspace_line(fact):
    level = "attention" if fact["state"] == "ok" and fact["stale"] else "info"
    symbol, label = level_info(level)
    return SummaryLine(level, symbol, str(label), airspace_text(fact))


def build_summary(
    now,
    forecast,
    events,
    city,
    *,
    gnss_enabled=True,
    forecast_checked_at=None,
    airspace=None,
):
    """El resumen del día para `city` a partir de UN pronóstico (o `None` si no hay).

    `now` es un instante aware; `events` los eventos ya detectados del pronóstico.
    """
    sunsets, zone = gnss.sunsets_from_forecast(forecast)
    local_now = now.astimezone(zone)
    today = local_now.date()
    sunrises = _sunrises(forecast, zone)
    sunrise = sunrises.get(today)
    sunset = sunsets.get(today)
    facts = _event_facts(events) if forecast else ()
    card = build_gnss_card(now, sunsets, city) if gnss_enabled else None

    lines = []
    if forecast:
        if facts:
            level = highest(fact["level"] for fact in facts)
            text = ngettext(
                "%(count)s weather event expected in 48 hours: %(names)s",
                "%(count)s weather events expected in 48 hours: %(names)s",
                len(facts),
            ) % {
                "count": len(facts),
                "names": ", ".join(str(fact["label"]) for fact in facts),
            }
        else:
            level = "info"
            text = _("No notable weather events expected in the next 48 hours")
    else:
        level, text = "info", _("The forecast is not available right now")
    symbol, label = level_info(level)
    lines.append(SummaryLine(level, symbol, str(label), text))
    gnss_line = None
    if card is not None:
        level = "attention" if card["status"] == "on" else "info"
        symbol, label = level_info(level)
        gnss_line = SummaryLine(level, symbol, str(label), _gnss_text(card))
        lines.append(gnss_line)

    airspace_line = None
    if airspace is not None:
        airspace_line = _airspace_line(airspace)
        lines.append(airspace_line)

    stale = bool(forecast_checked_at and now - forecast_checked_at > STALE_AFTER)
    return EnvironmentSummary(
        city=city,
        zone=zone,
        now=local_now,
        sunrise=sunrise,
        sunset=sunset,
        has_forecast=bool(forecast),
        events=facts,
        gnss=card,
        checked_at=forecast_checked_at,
        stale=stale,
        sunsets=sunsets,
        sunrises=sunrises,
        lines=tuple(lines),
        gnss_line=gnss_line,
        airspace=airspace,
        airspace_line=airspace_line,
    )
