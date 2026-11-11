"""LV-427: el formato normalizado de un log de vuelo, igual para cualquier fabricante.

Cada adaptador (DJI, sintético, a futuro Wingtra/PX4) traduce su archivo a `FlightTrack`; la
pantalla y el modelo sólo conocen esto. Todos los campos de un punto salvo `t` son opcionales: un
log puede no traer batería o satélites, y eso se muestra como «sin dato», no como cero.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

# Tope de puntos que se guardan y se dibujan: un log de 40 min a 10 Hz son 24 000 puntos y la
# pantalla no gana nada con ellos.
MAX_POINTS = 2000

LEVELS = ("info", "warning", "critical")

EARTH_RADIUS_M = 6_371_000.0


class FlightLogError(Exception):
    """Un log que no se pudo analizar, con un código estable que la pantalla traduce."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    INCOMPLETE = "incomplete"
    INSUFFICIENT_DATA = "insufficient_data"
    MISSING_API_KEY = "missing_api_key"
    PARSER_UNAVAILABLE = "parser_unavailable"
    CODES = (
        UNSUPPORTED_FORMAT,
        INCOMPLETE,
        INSUFFICIENT_DATA,
        MISSING_API_KEY,
        PARSER_UNAVAILABLE,
    )

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass
class TrackPoint:
    t: float
    lat: float | None = None
    lon: float | None = None
    height_m: float | None = None
    speed_ms: float | None = None
    battery_pct: float | None = None
    satellites: int | None = None


@dataclass
class FlightEvent:
    t: float
    level: str
    code: str
    raw_text: str
    explanation: str
    inferred: bool = False


@dataclass
class FlightSummary:
    started_at: str | None = None  # ISO 8601, con zona si se conoce
    timezone: str | None = None
    duration_s: float | None = None
    distance_m: float | None = None
    max_height_m: float | None = None
    max_speed_ms: float | None = None
    max_distance_from_takeoff_m: float | None = None
    takeoff: list[float] | None = None  # [lat, lon]
    landing: list[float] | None = None


@dataclass
class FlightTrack:
    points: list[TrackPoint] = field(default_factory=list)
    events: list[FlightEvent] = field(default_factory=list)
    summary: FlightSummary = field(default_factory=FlightSummary)
    uninterpreted: list[str] = field(default_factory=list)
    source_format: str = ""
    limitations: list[str] = field(default_factory=list)
    synthetic: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FlightTrack:
        return cls(
            points=[TrackPoint(**p) for p in data.get("points", [])],
            events=[FlightEvent(**e) for e in data.get("events", [])],
            summary=FlightSummary(**data.get("summary", {})),
            uninterpreted=list(data.get("uninterpreted", [])),
            source_format=data.get("source_format", ""),
            limitations=list(data.get("limitations", [])),
            synthetic=bool(data.get("synthetic", False)),
        )

    def downsampled(self, limit: int = MAX_POINTS) -> FlightTrack:
        """Una copia con a lo sumo `limit` puntos, conservando el primero y el último."""
        count = len(self.points)
        if count <= limit:
            return self
        step = (count - 1) / (limit - 1)
        picked = [self.points[round(i * step)] for i in range(limit)]
        copy = FlightTrack.from_dict(self.to_dict())
        copy.points = picked
        copy.limitations = [
            *self.limitations,
            f"points_downsampled:{count}:{limit}",
        ]
        return copy


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def build_summary(
    points: list[TrackPoint],
    started_at: str | None = None,
    timezone: str | None = None,
) -> FlightSummary:
    """Resumen calculado de los puntos (no tomado del log): distancia, alturas y velocidades."""
    located = [p for p in points if p.lat is not None and p.lon is not None]
    summary = FlightSummary(started_at=started_at, timezone=timezone)
    if points:
        summary.duration_s = round(points[-1].t - points[0].t, 1)
    heights = [p.height_m for p in points if p.height_m is not None]
    speeds = [p.speed_ms for p in points if p.speed_ms is not None]
    summary.max_height_m = max(heights) if heights else None
    summary.max_speed_ms = max(speeds) if speeds else None
    if located:
        first, last = located[0], located[-1]
        summary.takeoff = [first.lat, first.lon]
        summary.landing = [last.lat, last.lon]
        summary.distance_m = round(
            sum(
                haversine_m(a.lat, a.lon, b.lat, b.lon)
                for a, b in zip(located, located[1:])
            ),
            1,
        )
        summary.max_distance_from_takeoff_m = round(
            max(haversine_m(first.lat, first.lon, p.lat, p.lon) for p in located), 1
        )
    return summary
