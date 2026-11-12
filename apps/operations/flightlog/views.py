"""LV-427: pantalla «Flight analysis» de un log de vuelo adjunto a un permiso."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from apps.core.audit import set_audit_context
from apps.core.tenancy import scope_queryset_to_tenant
from apps.core.views import ModelViewPermissionRequiredMixin

from apps.registry.models import Aircraft, normalize_serial

from ..models import FlightLogAnalysis, FlightPermission, FlightRecord
from .charts import line_chart
from .compliance import check_flight, map_overlay
from .explanations import explain
from .independent import DJI_SERIAL_FIELD, back_link, serial_mismatch_warning
from .location import flight_place, place_note, place_sentence
from .narrative import build_narrative
from .types import FlightTrack, haversine_m

# Despegue y aterrizaje a menos de esta distancia se dibujan con un solo marcador.
SAME_SPOT_M = 15
PLACEHOLDER = "\0aircraft"


def _not_provided():
    return _("Not provided")


def error_text(code: str) -> str:
    """El mensaje legible de cada código de error del lector."""
    return {
        "unsupported_format": _(
            "This file is not a supported flight log format. Attach the original log file."
        ),
        "incomplete": _(
            "The log is incomplete or could not be read. Download it again from the "
            "aircraft or controller and attach it again."
        ),
        "insufficient_data": _(
            "The log does not have enough position data to draw a trajectory."
        ),
        "missing_api_key": _(
            "The DJI key needed to read this log is not configured on the server."
        ),
        "keychain_error": _(
            "DJI could not provide the keys to read this log. Check the server key and its "
            "internet access, then try again."
        ),
        "parser_unavailable": _(
            "The DJI log reader is not installed yet, so this log cannot be analysed for now."
        ),
    }.get(code, _("The log could not be analysed."))


def _clock(seconds):
    if seconds is None:
        return None
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_moment(iso):
    """`2026-09-18T12:26:48-03:00` -> `18-09-2026 12:26:48` (una sola fecha d-m-Y); lo que no
    se puede leer queda como vino."""
    if not iso:
        return None
    try:
        return f"{datetime.fromisoformat(iso):%d-%m-%Y %H:%M:%S}"
    except ValueError:
        return iso


def _num(value, unit, digits=1):
    if value is None:
        return None
    return f"{value:,.{digits}f} {unit}"


def _summary_rows(track: FlightTrack):
    s = track.summary
    tz = s.timezone or _("time zone not determined")
    start = f"{format_moment(s.started_at)} ({tz})" if s.started_at else None
    speed = None
    if s.max_speed_ms is not None:
        speed = f"{s.max_speed_ms:.1f} m/s ({s.max_speed_ms * 3.6:.1f} km/h)"
    distance = None
    if s.distance_m is not None:
        distance = f"{s.distance_m:,.0f} m"
    take = f"{s.takeoff[0]:.5f}, {s.takeoff[1]:.5f}" if s.takeoff else None
    land = f"{s.landing[0]:.5f}, {s.landing[1]:.5f}" if s.landing else None
    utc = f"{format_moment(s.started_at_utc)} (UTC)" if s.started_at_utc else None
    return [
        (_("Start"), start),
        (_("Start (UTC)"), utc),
        (_("Duration (min:s)"), _clock(s.duration_s)),
        (_("Distance flown"), distance),
        (_("Maximum height above takeoff"), _num(s.max_height_m, "m")),
        (_("Maximum speed"), speed),
        (
            _("Maximum distance from takeoff"),
            _num(s.max_distance_from_takeoff_m, "m", 0),
        ),
        (_("Takeoff point (lat, lon)"), take),
        (_("Landing point (lat, lon)"), land),
    ]


def _nearest_position(track: FlightTrack, t: float):
    located = [p for p in track.points if p.lat is not None and p.lon is not None]
    if not located:
        return None
    best = min(located, key=lambda p: abs(p.t - t))
    return best.lat, best.lon


def registry_aircraft(track: FlightTrack, tenant_id):
    """La aeronave del registro con el número de serie que dice el log, **sólo de este tenant**.

    La normalización es la de `apps.registry` (mayúsculas, sin espacios) y no hay coincidencia
    aproximada: sin serie exacta no hay aeronave, y no se supone ninguna.
    """
    serial = normalize_serial((track.aircraft or {}).get("serial"))
    if not serial:
        return None
    fleet = Aircraft.objects.filter(tenant_id=tenant_id).select_related("cost_center")
    exact = fleet.filter(serial_number=serial).first()
    if exact or len(serial) != DJI_SERIAL_FIELD:
        return exact
    # Serie cortada por el formato DJI (LV-434): vale sólo si una única aeronave empieza así.
    candidates = list(fleet.filter(serial_number__startswith=serial)[:2])
    return candidates[0] if len(candidates) == 1 else None


def _return_path(track: FlightTrack):
    leg = track.return_leg
    if not leg:
        return []
    return [
        [p.lat, p.lon]
        for p in track.points
        if p.lat is not None and p.lon is not None and leg[0] <= p.t <= leg[1]
    ]


def _same_spot(track: FlightTrack) -> bool:
    take, land = track.summary.takeoff, track.summary.landing
    return bool(take and land and haversine_m(*take, *land) < SAME_SPOT_M)


def map_payload(track: FlightTrack) -> dict:
    """Lo que dibuja `flight-analysis.js`: sólo datos, entregados por `json_script`."""
    located = [p for p in track.points if p.lat is not None and p.lon is not None]
    events = []
    for event in track.events:
        if event.level not in ("warning", "critical"):
            continue
        pos = _nearest_position(track, event.t)
        if pos:
            events.append(
                {
                    "lat": pos[0],
                    "lon": pos[1],
                    "level": event.level,
                    "when": _clock(event.t),
                    "text": explain(event.code, event.explanation) or event.raw_text,
                }
            )
    return {
        "tiles": settings.GEO_TILE_PROVIDERS,
        "points": [[p.lat, p.lon, p.height_m] for p in located],
        "takeoff": track.summary.takeoff,
        "landing": track.summary.landing,
        "events": events,
        "returnPath": _return_path(track),
        "sameSpot": _same_spot(track),
        "i18n": {
            "takeoffLanding": _("Takeoff and landing"),
            "returnLeg": _("Automatic return"),
            "takeoff": _("Takeoff"),
            "landing": _("Landing"),
            "height": _("Height above takeoff (m)"),
            "noHeight": _("Height not recorded"),
            "critical": _("Critical"),
            "warning": _("Warning"),
            "authorizedArea": _("Authorized area"),
            "outsideArea": _("Outside the authorized area"),
            "overHeight": _("Over the authorized height"),
        },
    }


def _charts(track: FlightTrack):
    x = _("Time (min:s)")

    def series(attr):
        return [
            (p.t, getattr(p, attr))
            for p in track.points
            if getattr(p, attr) is not None
        ]

    return [
        {
            "key": "height",
            "title": _("Height over time"),
            "svg": line_chart(series("height_m"), _("Height (m)"), x),
            "note": _(
                "Height above the takeoff point. A steady climb, a plateau and a descent "
                "is a normal flight."
            ),
        },
        {
            "key": "speed",
            "title": _("Speed over time"),
            "svg": line_chart(series("speed_ms"), _("Speed (m/s)"), x),
            "note": _(
                "Ground speed. Sudden peaks can point to strong wind or a fast manoeuvre."
            ),
        },
        {
            "key": "battery",
            "title": _("Battery over time"),
            "svg": line_chart(series("battery_pct"), _("Battery (%)"), x),
            "note": _(
                "Remaining battery charge. It should fall steadily; a sharp drop deserves a look."
            ),
        },
    ]


def _event_rows(track: FlightTrack):
    levels = {
        "info": _("Info"),
        "warning": _("Warning"),
        "critical": _("Critical"),
    }
    return [
        {
            "time": _clock(e.t),
            "level": e.level,
            "level_label": levels.get(e.level, e.level),
            "explanation": explain(e.code, e.explanation),
            "raw_text": e.raw_text,
            "inferred": e.inferred,
        }
        for e in track.events
    ]


def _limitation_text(item: str) -> str:
    if item == "synthetic_example_data":
        return _("Synthetic example data: not a real flight.")
    if item.startswith("points_downsampled:"):
        _tag, total, kept = item.split(":")
        return _("The trajectory was thinned from %(total)s to %(kept)s points.") % {
            "total": total,
            "kept": kept,
        }
    return item


class AnalysisLookupMixin:
    """El análisis de la URL, siempre acotado al tenant del permiso (404 si es de otro)."""

    def has_permission(self):
        # LV-431: quien ve la sección «Flight logs» abre el análisis sin pedir además `view_flightrecord`.
        user = self.request.user
        return user.has_perm("operations.view_flightrecord") or user.has_perm(
            "operations.view_flightloganalysis"
        )

    def get_analysis(self) -> FlightLogAnalysis:
        queryset = scope_queryset_to_tenant(
            FlightLogAnalysis.objects.filter(is_active=True).select_related(
                "permission",
                "cost_center",
                "aircraft",
                "flight_record__aircraft",
                "flight_record__pilot",
                "document",
            ),
            self.request.user,
            "cost_center__tenant_id",
        )
        try:
            return queryset.get(pk=self.kwargs["pk"])
        except FlightLogAnalysis.DoesNotExist as exc:
            raise Http404 from exc


class FlightAnalysisView(
    AnalysisLookupMixin, ModelViewPermissionRequiredMixin, TemplateView
):
    """Lectura: `view_flightrecord` y el tenant del permiso. El enlace a una operación
    (POST) exige además `change_flightrecord`."""

    model = FlightRecord
    template_name = "operations/flight_analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analysis = self.get_analysis()
        permission = analysis.permission
        record = analysis.flight_record
        missing = _not_provided()
        operation = [
            (
                _("Permit"),
                (permission.permission_number or str(permission))
                if permission
                else missing,
            ),
            (_("Cost center"), str(analysis.cost_center)),
            (_("Aircraft"), PLACEHOLDER),
            (_("Operator"), str(record.pilot) if record else missing),
            (
                _("Date"),
                record.actual_date.strftime("%d-%m-%Y") if record else missing,
            ),
        ]
        context.update(
            {
                "analysis": analysis,
                "permission": permission,
                "record": record,
                "not_provided": missing,
                "records": list(
                    permission.records.filter(is_active=True).order_by(
                        "-actual_date", "-departure_time"
                    )
                )
                if permission
                else [],
                "back": back_link(analysis),
                "can_link": self.request.user.has_perm(
                    "operations.change_flightrecord"
                ),
                "permit_choices": self._permit_choices(analysis),
            }
        )
        ok = analysis.status == FlightLogAnalysis.STATUS_OK
        context["operation"] = self._with_aircraft(
            operation,
            FlightTrack.from_dict(analysis.result) if ok else FlightTrack(),
            analysis,
            record,
        )
        if analysis.status == FlightLogAnalysis.STATUS_ERROR:
            context["error_text"] = error_text(analysis.error_code)
        elif analysis.status == FlightLogAnalysis.STATUS_OK:
            track = FlightTrack.from_dict(analysis.result)
            result = check_flight(
                track,
                permission,
                with_plans=self.request.user.has_perm("geo.view_geoplan"),
            )
            map_data = map_payload(track)
            map_data["compliance"] = map_overlay(result)
            place = flight_place(track)
            context.update(
                {
                    "place": place,
                    "place_sentence": place_sentence(place),
                    "place_note": place_note(),
                    "compliance": result,
                    "serial_warning": serial_mismatch_warning(analysis, track),
                    "narrative": build_narrative(track),
                    "has_return": bool(track.return_leg),
                    "track": track,
                    "summary_rows": _summary_rows(track),
                    "map_data": map_data,
                    "has_map": any(
                        p.lat is not None and p.lon is not None for p in track.points
                    ),
                    "charts": _charts(track),
                    "event_rows": _event_rows(track),
                    "limitations": [_limitation_text(i) for i in track.limitations],
                    "uninterpreted": track.uninterpreted,
                }
            )
        return context

    def _permit_choices(self, analysis):
        """Permisos que se pueden vincular a un análisis sin permiso: sólo los de su centro de
        costo (y por tanto de su tenant), y sólo a quien puede modificar el análisis."""
        if (
            analysis.permission_id
            or analysis.cost_center_id is None
            or not self.request.user.has_perm("operations.change_flightloganalysis")
        ):
            return []
        return list(
            FlightPermission.objects.filter(
                is_active=True, cost_center_id=analysis.cost_center_id
            ).order_by("-created_at")
        )

    def _link_permit(self, request):
        if not request.user.has_perm("operations.change_flightloganalysis"):
            raise PermissionDenied
        analysis = self.get_analysis()
        if analysis.permission_id or analysis.cost_center_id is None:
            raise Http404
        try:
            pk = uuid.UUID(request.POST.get("permission", ""))
        except ValueError as exc:
            raise Http404 from exc
        permit = FlightPermission.objects.filter(
            is_active=True, cost_center_id=analysis.cost_center_id, pk=pk
        ).first()
        if permit is None:
            raise Http404
        analysis.permission = permit
        analysis.save(update_fields=["permission", "updated_at"])
        set_audit_context(request, analysis, action="update")
        messages.success(request, _("Permit linked to the flight log."))
        return redirect("flight-analysis", pk=analysis.pk)

    def _with_aircraft(self, operation, track, analysis, record):
        """Rellena la fila «Aircraft»: registro (por serie) > operación enlazada > «Not provided»,
        más el modelo que dice el log marcado como tal. Nunca se inventa un dato."""
        missing = _not_provided()
        matched = analysis.aircraft or registry_aircraft(
            track, analysis.cost_center.tenant_id
        )
        log_model = (track.aircraft or {}).get("log_model")
        extra = []
        if matched is not None:
            aircraft = f"{matched.registration} · {matched.model}"
            extra.append(
                (
                    _("Aircraft cost center"),
                    str(matched.cost_center) if matched.cost_center else missing,
                )
            )
        elif record:
            aircraft = f"{record.aircraft.registration} · {record.aircraft.model}"
        else:
            aircraft = missing
        if matched is None and log_model:
            aircraft = f"{aircraft} · {log_model} ({_('according to the log')})"
        rows = []
        for label, value in operation:
            if value == PLACEHOLDER:
                rows += [(label, aircraft), *extra]
            else:
                rows.append((label, value))
        return rows

    def post(self, request, *args, **kwargs):
        if "permission" in request.POST:
            return self._link_permit(request)
        if not request.user.has_perm("operations.change_flightrecord"):
            raise PermissionDenied
        analysis = self.get_analysis()
        if analysis.permission is None:
            raise Http404
        pk = request.POST.get("flight_record", "")
        if pk == "":
            record = None
        else:
            try:
                uuid.UUID(pk)
            except ValueError as exc:
                raise Http404 from exc
            record = analysis.permission.records.filter(is_active=True, pk=pk).first()
            if record is None:
                raise Http404
        analysis.flight_record = record
        analysis.save(update_fields=["flight_record", "updated_at"])
        set_audit_context(request, analysis, action="update")
        messages.success(request, _("Operation linked to the flight log."))
        return redirect("flight-analysis", pk=analysis.pk)
