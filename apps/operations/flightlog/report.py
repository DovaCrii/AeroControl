"""LV-430: reporte de vuelo imprimible (formato J.E.J.), KML y CSV de un log analizado.

El PDF no se genera en el servidor: la vista imprimible es la misma pantalla con la hoja de estilos
de impresión y el navegador la guarda como PDF, con el mapa satelital tal como se ve.
"""

from __future__ import annotations

import csv
from datetime import datetime

from django.http import Http404, HttpResponse
from django.utils.html import escape
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.generic import View

from apps.core import branding
from apps.core.exports import neutralize
from apps.core.views import ModelViewPermissionRequiredMixin

from ..models import FlightLogAnalysis, FlightRecord
from .compliance import timeline_flags
from .explanations import explain
from .narrative import _final_battery
from .service import PARSER_VERSION
from .timeline import phase_segments, timeline_svg
from .types import FlightTrack
from .views import (
    AnalysisLookupMixin,
    FlightAnalysisView,
    _clock,
    _nearest_position,
    _not_provided,
    registry_aircraft,
)

LOW_BATTERY_CODES = ("tip:low_battery_rth", "warn:low_battery_rth")
CSV_COLUMNS = (
    "t_s",
    "lat",
    "lon",
    "height_m",
    "speed_ms",
    "battery_pct",
    "satellites",
)


def csv_cell(value):
    """Un número va como número (un `-33.4` de latitud no es una fórmula y `neutralize` lo
    rompería con un apóstrofo); el texto pasa por `neutralize`."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return neutralize(value)


def _aircraft_facts(track: FlightTrack, permission, record):
    """Matrícula, modelo y serie: del registro si hubo cruce por serie (o de la operación
    enlazada); si no, lo que dice el log, marcado como tal."""
    missing = _not_provided()
    log = track.aircraft or {}
    known = registry_aircraft(track, permission.cost_center.tenant_id)
    if known is None and record is not None:
        known = record.aircraft
    if known is not None:
        return {
            "registration": known.registration,
            "model": known.model,
            "serial": known.serial_number,
            "from_log": False,
        }
    note = f" ({_('according to the log')})"
    return {
        "registration": missing,
        "model": f"{log['log_model']}{note}" if log.get("log_model") else missing,
        "serial": f"{log['serial']}{note}" if log.get("serial") else missing,
        "from_log": True,
    }


def _local_start(track: FlightTrack):
    s = track.summary
    if not s.started_at:
        return None
    try:
        moment = datetime.fromisoformat(s.started_at)
    except ValueError:
        return s.started_at
    tz = f" ({s.timezone})" if s.timezone else ""
    return f"{moment:%d-%m-%Y %H:%M}{tz}"


def _kpis(track: FlightTrack):
    s = track.summary
    battery = _final_battery(track)
    return [
        {
            "label": _("Duration"),
            "value": _clock(s.duration_s),
            "unit": _("min:s"),
        },
        {
            "label": _("Distance flown"),
            "value": None if s.distance_m is None else f"{s.distance_m:,.0f}",
            "unit": "m",
        },
        {
            "label": _("Maximum height"),
            "value": None if s.max_height_m is None else f"{s.max_height_m:.0f}",
            "unit": "m",
        },
        {
            "label": _("Final battery"),
            "value": None if battery is None else f"{battery:.0f}",
            "unit": "%",
        },
    ]


def _peak(points, attr):
    values = [(p.t, getattr(p, attr)) for p in points if getattr(p, attr) is not None]
    return max(values, key=lambda item: item[1]) if values else None


def _readings(track: FlightTrack) -> dict:
    """Una frase de lectura por gráfico, escrita sólo con hechos del log."""
    out = {"height": "", "speed": "", "battery": ""}
    top = _peak(track.points, "height_m")
    if top:
        out["height"] = _(
            "Maximum height: %(max)s m above takeoff, reached at %(time)s."
        ) % {"max": f"{top[1]:.0f}", "time": _clock(top[0])}
    fast = _peak(track.points, "speed_ms")
    if fast:
        speeds = [p.speed_ms for p in track.points if p.speed_ms is not None]
        out["speed"] = _(
            "Top speed: %(ms)s m/s (%(kmh)s km/h) at %(time)s; average %(avg)s m/s."
        ) % {
            "ms": f"{fast[1]:.1f}",
            "kmh": f"{fast[1] * 3.6:.0f}",
            "time": _clock(fast[0]),
            "avg": f"{sum(speeds) / len(speeds):.1f}",
        }
    levels = [p for p in track.points if p.battery_pct is not None]
    if levels:
        text = _("The battery went from %(start)s%% to %(end)s%%.") % {
            "start": f"{levels[0].battery_pct:.0f}",
            "end": f"{levels[-1].battery_pct:.0f}",
        }
        warned = next((e for e in track.events if e.code in LOW_BATTERY_CODES), None)
        if warned is not None:
            near = min(levels, key=lambda p: abs(p.t - warned.t))
            text += " " + _("The aircraft warned at %(time)s, with %(pct)s%% left.") % {
                "time": _clock(warned.t),
                "pct": f"{near.battery_pct:.0f}",
            }
        out["battery"] = text
    return out


def _timeline(track: FlightTrack, flags=()):
    labels = {
        "area": _("Outside the authorized area"),
        "height": _("Over the authorized height"),
        "title": _("Flight phases and warnings"),
        "takeoff": _("Takeoff"),
        "work": _("Work"),
        "return": _("Automatic return"),
        "landing": _("Landing"),
        "time": _("Time (min:s)"),
    }

    def mark_text(t, level, raw):
        name = _("Critical") if level == "critical" else _("Warning")
        return f"{name} {_clock(t)}: {raw}"

    legend = [
        (phase, labels[phase])
        for phase in dict.fromkeys(p for p, *_r in phase_segments(track))
    ]
    return timeline_svg(track, labels, mark_text, flags), legend


def _file_slug(analysis, track, facts) -> str:
    plate = facts["registration"] if not facts["from_log"] else None
    log_model = (track.aircraft or {}).get("log_model")
    day = (track.summary.started_at or "")[:10] or (
        analysis.analyzed_at.strftime("%Y-%m-%d") if analysis.analyzed_at else "log"
    )
    return slugify(f"flight {day} {plate or log_model or 'aircraft'}")


class FlightReportView(FlightAnalysisView):
    """La pantalla «Flight analysis» en versión para imprimir (A4). Mismo permiso y tenant."""

    template_name = "operations/flight_report.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analysis = context["analysis"]
        if analysis.status != FlightLogAnalysis.STATUS_OK:
            raise Http404
        track = context["track"]
        facts = _aircraft_facts(track, analysis.permission, analysis.flight_record)
        compliance = context["compliance"]
        svg, legend = _timeline(track, timeline_flags(compliance))
        charts = context["charts"]
        readings = _readings(track)
        for chart in charts:
            chart["reading"] = readings.get(chart["key"], "")
        record = analysis.flight_record
        missing = context["not_provided"]
        start = _local_start(track)
        context.update(
            {
                "logo_static": branding.LOGO_STATIC_PATH,
                "aircraft": facts,
                "header_aircraft": (
                    f"{facts['registration']} · {facts['model']}"
                    if not facts["from_log"]
                    else facts["model"]
                ),
                "start_text": start or missing,
                "kpis": _kpis(track),
                "timeline": svg,
                "timeline_flagged": bool(compliance["segments"]),
                "timeline_legend": legend,
                "charts": charts,
                "operator": str(record.pilot) if record else missing,
                "record_date": record.actual_date.strftime("%d-%m-%Y")
                if record
                else missing,
                "parser_version": PARSER_VERSION,
                "analysis_parser_version": analysis.parser_version or missing,
                "source_format": track.source_format or missing,
                "low_battery": context["narrative"]["low_battery"],
            }
        )
        return context


class _ExportView(AnalysisLookupMixin, ModelViewPermissionRequiredMixin, View):
    model = FlightRecord

    def get(self, request, *args, **kwargs):
        analysis = self.get_analysis()
        if analysis.status != FlightLogAnalysis.STATUS_OK:
            raise Http404
        track = FlightTrack.from_dict(analysis.result)
        facts = _aircraft_facts(track, analysis.permission, analysis.flight_record)
        return self.render(analysis, track, facts, _file_slug(analysis, track, facts))


class FlightCsvView(_ExportView):
    """Una fila por punto guardado (el log ya viene reducido a 2000 puntos como máximo)."""

    def render(self, analysis, track, facts, slug):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
        writer = csv.writer(response)
        writer.writerow([neutralize(name) for name in CSV_COLUMNS])
        for p in track.points:
            writer.writerow(
                [
                    csv_cell(value)
                    for value in (
                        p.t,
                        p.lat,
                        p.lon,
                        p.height_m,
                        p.speed_ms,
                        p.battery_pct,
                        p.satellites,
                    )
                ]
            )
        return response


def _coords(track: FlightTrack, relative: bool) -> str:
    return " ".join(
        f"{p.lon:.7f},{p.lat:.7f},{(p.height_m or 0.0) if relative else 0:.1f}"
        for p in track.points
        if p.lat is not None and p.lon is not None
    )


def _placemark(name, description, lat, lon, style=""):
    return (
        f"<Placemark><name>{escape(name)}</name>"
        f"<description>{escape(description)}</description>{style}"
        f"<Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point></Placemark>"
    )


class FlightKmlView(_ExportView):
    """Trayectoria como LineString y marcas de despegue, aterrizaje y avisos.

    Altitud: el log sólo trae la altura **sobre el punto de despegue**, no una altitud absoluta
    fiable, así que es `relativeToGround` (metros sobre el terreno bajo cada punto, que en el
    despegue es 0). Un log sin altura se dibuja `clampToGround`.
    """

    def render(self, analysis, track, facts, slug):
        located = [p for p in track.points if p.lat is not None and p.lon is not None]
        if len(located) < 2:
            raise Http404
        relative = any(p.height_m is not None for p in located)
        mode = "relativeToGround" if relative else "clampToGround"
        s = track.summary
        title = (
            f"{_('Flight report')} {facts['registration']} {s.started_at or ''}".strip()
        )
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
            f"<name>{escape(title)}</name>",
            # KML escribe el color como aabbggrr: #1E418C (azul J.E.J.) -> ff8c411e.
            '<Style id="path"><LineStyle><color>ff8c411e</color><width>4</width></LineStyle></Style>',
            f"<Placemark><name>{escape(_('Flight path'))}</name><styleUrl>#path</styleUrl>"
            f"<LineString><altitudeMode>{mode}</altitudeMode>"
            f"<coordinates>{_coords(track, relative)}</coordinates></LineString></Placemark>",
        ]
        if s.takeoff:
            parts.append(_placemark(_("Takeoff"), "", *s.takeoff))
        if s.landing:
            parts.append(_placemark(_("Landing"), "", *s.landing))
        for event in track.events:
            if event.level not in ("warning", "critical"):
                continue
            where = _nearest_position(track, event.t)
            if where:
                label = _("Critical") if event.level == "critical" else _("Warning")
                parts.append(
                    _placemark(
                        f"{label} {_clock(event.t)}",
                        f"{explain(event.code, event.explanation)}\n{event.raw_text}",
                        *where,
                    )
                )
        parts.append("</Document></kml>")
        response = HttpResponse(
            "".join(parts), content_type="application/vnd.google-earth.kml+xml"
        )
        response["Content-Disposition"] = f'attachment; filename="{slug}.kml"'
        return response
