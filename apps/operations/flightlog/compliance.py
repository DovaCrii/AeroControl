"""LV-432: ¿voló dentro de lo que la DGAC autorizó? El área y la altura del permiso contra el log.

Todo se calcula en el servidor, con los puntos ya guardados del análisis:

* **Área**: la geometría del plan KMZ vinculado al permiso (`apps.geo.mini_map.plan_area`, la misma
  que dibuja el mapa de espacio aéreo; el círculo de Trimble llega como `LineString` cerrado y ahí
  ya viene convertido en polígono) o, sin plan, el círculo del propio permiso (centro + radio).
  Un punto está *fuera* si queda a más de `AREA_TOLERANCE_M` del borde: la tolerancia absorbe el
  error de posición del GPS (típicamente de 2 a 5 m) y el redondeo del KMZ. Se configura con
  `settings.FLIGHT_LOG_AREA_TOLERANCE_M`.
* **Altura**: `FlightPermission.max_altitude_m` (metros; `max_altitude_ft` está retirado y no se
  lee). ⚠️ El log trae la altura **sobre el punto de despegue**, no sobre el terreno (AGL) ni sobre
  el nivel del mar (ASL): si el terreno sube o baja respecto del despegue, la altura real sobre el
  suelo es otra. Por eso la comparación lleva siempre esa salvedad y el veredicto dice «según el
  log», nunca «incumplió».
* **Tiempo**: cada punto representa el intervalo hasta los puntos vecinos (la mitad hacia cada
  lado), así que un tramo de varios puntos suma segundos y un punto aislado suma el medio paso.

Un tramo de 5 s o más es «critical»; uno más corto es «warning» (puede ser ruido de posición).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import gettext as _

from apps.geo.mini_map import plan_area

from .types import EARTH_RADIUS_M, FlightTrack, haversine_m

AREA_TOLERANCE_M = 10.0
SUSTAINED_S = 5.0
KIND_PLAN, KIND_CIRCLE = "plan", "circle"


def area_tolerance_m() -> float:
    return float(getattr(settings, "FLIGHT_LOG_AREA_TOLERANCE_M", AREA_TOLERANCE_M))


# ── geometría ────────────────────────────────────────────────────────────────


def _rings(shapes):
    """Los polígonos GeoJSON como `[[anillo exterior, *huecos]]`, cada anillo `[(lat, lon)]`."""
    polygons = []
    for shape in shapes:
        kind, coords = shape.get("type"), shape.get("coordinates") or []
        if kind == "Polygon":
            groups = [coords]
        elif kind == "MultiPolygon":
            groups = coords
        else:
            continue
        for group in groups:
            rings = [[(v[1], v[0]) for v in ring] for ring in group if len(ring) >= 4]
            if rings:
                polygons.append(rings)
    return polygons


def _local(lat0, lon0, lat, lon):
    """Metros (este, norte) de `(lat, lon)` respecto de `(lat0, lon0)`; plano local."""
    k = EARTH_RADIUS_M * math.pi / 180
    return (lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k


def _inside(ring):
    """¿El origen está dentro del anillo `[(x, y)]`? (par-impar)"""
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > 0) != (y2 > 0) and x1 + (0 - y1) * (x2 - x1) / (y2 - y1) > 0:
            inside = not inside
    return inside


def _edge_distance(ring):
    """Distancia del origen al borde del anillo `[(x, y)]`."""
    best = math.inf
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        u = 0.0 if not length2 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length2))
        best = min(best, math.hypot(x1 + u * dx, y1 + u * dy))
    return best


def distance_outside_m(lat, lon, polygons) -> float:
    """0 si el punto cae dentro de algún polígono; si no, los metros hasta el más cercano."""
    best = math.inf
    for rings in polygons:
        local = [[_local(lat, lon, *v) for v in ring] for ring in rings]
        if _inside(local[0]) and not any(_inside(hole) for hole in local[1:]):
            return 0.0
        best = min(best, min(_edge_distance(ring) for ring in local))
    return best


# ── el área autorizada del permiso ──────────────────────────────────────────


@dataclass
class AuthorizedArea:
    kind: str | None = None  # "plan" | "circle"
    polygons: list = field(default_factory=list)  # [[anillo, *huecos]] con (lat, lon)
    circle: dict | None = None  # {lat, lon, radius_m}
    reason: str | None = None  # por qué no hay con qué comparar

    @property
    def available(self) -> bool:
        return self.kind is not None

    def distance_outside(self, lat, lon) -> float:
        if self.kind == KIND_CIRCLE:
            c = self.circle
            return max(0.0, haversine_m(lat, lon, c["lat"], c["lon"]) - c["radius_m"])
        return distance_outside_m(lat, lon, self.polygons)

    def payload(self) -> dict | None:
        """Lo que dibuja el mapa, en `[lat, lon]` (el orden de Leaflet)."""
        if not self.available:
            return None
        return {
            "kind": self.kind,
            "polygons": [
                [[list(v) for v in ring] for ring in poly] for poly in self.polygons
            ],
            "circle": self.circle,
        }


def authorized_area(permission, with_plans: bool) -> AuthorizedArea:
    """El área que dice el permiso: su plan KMZ (si quien mira puede ver planes) o su círculo.

    Mismo criterio que el mapa de espacio aéreo (`apps.airspace.views.permit_area`): la geometría
    del plan sólo viaja con `geo.view_geoplan`; sin ella el permiso cae a su propio círculo.
    """
    if permission is None:
        return AuthorizedArea(reason=_("The flight log is not linked to a permit."))
    if with_plans:
        plans = permission.geo_plans.filter(
            is_active=True, current_version__isnull=False
        ).select_related("current_version")
        shapes = []
        for plan in plans.order_by("created_at", "pk"):
            found, _center = plan_area(plan.current_version.content)
            shapes.extend(found)
        polygons = _rings(shapes)
        if polygons:
            return AuthorizedArea(kind=KIND_PLAN, polygons=polygons)
    lat, lon, radius = permission.latitude, permission.longitude, permission.radius_km
    if lat is not None and lon is not None and radius:
        return AuthorizedArea(
            kind=KIND_CIRCLE,
            circle={
                "lat": float(lat),
                "lon": float(lon),
                "radius_m": float(radius) * 1000,
            },
        )
    return AuthorizedArea(
        reason=_(
            "The permit has no area geometry (no KMZ plan and no centre with radius)."
        )
    )


# ── tramos ───────────────────────────────────────────────────────────────────


def _runs(flags):
    """Tramos consecutivos de índices con bandera: `[(primero, último)]`."""
    runs, start = [], None
    for i, flagged in enumerate(flags):
        if flagged and start is None:
            start = i
        if start is not None and (not flagged or i == len(flags) - 1):
            runs.append((start, i if flagged else i - 1))
            start = None
    return runs


def _cover(times, i):
    """Segundos que representa el punto `i`: la mitad de cada intervalo vecino."""
    before = (times[i] - times[i - 1]) / 2 if i > 0 else 0.0
    after = (times[i + 1] - times[i]) / 2 if i + 1 < len(times) else 0.0
    return before + after


def _segments(points, values, limit):
    """Tramos donde `values[i] > limit`: `{start, end, seconds, peak, path}`."""
    times = [p.t for p in points]
    out = []
    for first, last in _runs([v is not None and v > limit for v in values]):
        out.append(
            {
                "start": times[first],
                "end": times[last],
                "seconds": round(
                    sum(_cover(times, i) for i in range(first, last + 1)), 1
                ),
                "peak": round(max(values[first : last + 1]), 1),
                "path": [
                    [p.lat, p.lon]
                    for p in points[max(0, first - 1) : last + 2]
                    if p.lat is not None and p.lon is not None
                ],
            }
        )
    return out


def _level(*groups) -> str:
    segments = [s for g in groups for s in g]
    if not segments:
        return "ok"
    return (
        "critical" if any(s["seconds"] >= SUSTAINED_S for s in segments) else "warning"
    )


def _clock(seconds) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def check_flight(track: FlightTrack, permission, with_plans: bool = True) -> dict:
    """El resultado completo: veredicto, cifras, tramos y salvedades. Siempre devuelve un dict."""
    area = authorized_area(permission, with_plans)
    limit = getattr(permission, "max_altitude_m", None)
    located = [p for p in track.points if p.lat is not None and p.lon is not None]
    tol = area_tolerance_m()

    area_segments, area_checked = [], area.available and bool(located)
    if area_checked:
        outside = [area.distance_outside(p.lat, p.lon) for p in located]
        area_segments = _segments(located, outside, tol)
        area_segments = [{**s, "kind": "area"} for s in area_segments]
    height_checked = limit is not None and any(
        p.height_m is not None for p in track.points
    )
    height_segments = []
    if height_checked:
        height_segments = [
            {**s, "kind": "height"}
            for s in _segments(
                track.points, [p.height_m for p in track.points], float(limit)
            )
        ]

    reasons = []
    if not area.available:
        reasons.append(area.reason)
    elif not located:
        reasons.append(_("The log has no position data to compare with the area."))
    if limit is None and permission is not None:
        reasons.append(_("The permit has no maximum altitude registered."))
    elif limit is not None and not height_checked:
        reasons.append(
            _("The log has no height data to compare with the altitude limit.")
        )

    if not (area_checked or height_checked):
        return {
            "available": False,
            "level": "info",
            "verdict": _("No authorized area to compare"),
            "reasons": reasons,
            "lines": [],
            "area": None,
            "height": None,
            "segments": [],
            "caveats": [],
            "tolerance_m": tol,
            "limit_m": limit,
        }

    out_s = round(sum(s["seconds"] for s in area_segments), 1)
    out_max = max((s["peak"] for s in area_segments), default=0.0)
    over_s = round(sum(s["seconds"] for s in height_segments), 1)
    over_max = max((s["peak"] for s in height_segments), default=0.0)

    lines = []
    if area_checked:
        lines.append(
            _(
                "The aircraft left the authorized area for %(seconds)s s (up to %(meters)s m outside)."
            )
            % {"seconds": f"{out_s:.0f}", "meters": f"{out_max:.0f}"}
            if area_segments
            else _("The whole flight stayed inside the authorized area.")
        )
    if height_checked:
        lines.append(
            _(
                "The aircraft exceeded the authorized height of %(limit)s m for %(seconds)s s (up to %(peak)s m above takeoff)."
            )
            % {"limit": limit, "seconds": f"{over_s:.0f}", "peak": f"{over_max:.0f}"}
            if height_segments
            else _(
                "The whole flight stayed under the authorized height of %(limit)s m."
            )
            % {"limit": limit}
        )
    level = _level(area_segments, height_segments)
    if level == "ok":
        # Con una sola de las dos comparaciones no se declara «todo bien».
        verdict = (
            _("Inside the area and under the height for the whole flight")
            if area_checked and height_checked
            else _("No deviation found in the comparison that could be made")
        )
    elif area_segments and height_segments:
        verdict = _("Outside the area and over the height, according to the log")
    elif area_segments:
        verdict = _("Left the authorized area, according to the log")
    else:
        verdict = _("Exceeded the authorized height, according to the log")

    caveats = [
        _(
            "Position accuracy: GPS error is typically a few metres, so a point is counted as outside only beyond %(tol)s m from the area edge."
        )
        % {"tol": f"{tol:.0f}"},
        _(
            "Height reference: the log records height above the takeoff point, not above the ground or sea level. If the terrain differs from the takeoff point, the real height above ground differs from what is compared here."
        ),
        _(
            "This comparison is an aid to review the flight; it does not replace the pilot's report or the DGAC's assessment."
        ),
    ]
    return {
        "available": True,
        "level": level,
        "verdict": verdict,
        "reasons": reasons,
        "lines": lines,
        "area": {
            "checked": area_checked,
            "kind": area.kind,
            "outside_s": out_s,
            "max_outside_m": round(out_max, 1),
            "payload": area.payload(),
        },
        "height": {
            "checked": height_checked,
            "limit_m": limit,
            "over_s": over_s,
            "max_over_height_m": round(over_max, 1),
        },
        "segments": [*area_segments, *height_segments],
        "segment_text": [
            f"{_clock(s['start'])}-{_clock(s['end'])} · "
            + (_("outside the area") if s["kind"] == "area" else _("over the height"))
            for s in [*area_segments, *height_segments]
        ],
        "caveats": caveats,
        "tolerance_m": tol,
        "limit_m": limit,
    }


def map_overlay(result: dict) -> dict:
    """Lo del resultado que dibuja `flight-analysis.js` (sólo datos, por `json_script`)."""
    area = (result.get("area") or {}).get("payload")
    return {
        "area": area,
        "outside": [s["path"] for s in result["segments"] if s["kind"] == "area"],
        "over": [s["path"] for s in result["segments"] if s["kind"] == "height"],
    }


def timeline_flags(result: dict):
    """`[(inicio, fin, 'area'|'height')]` para marcar la línea de tiempo del reporte."""
    return [(s["start"], s["end"], s["kind"]) for s in result["segments"]]
