"""LV-427: adaptadores de formato. Cada uno decide si reconoce el archivo y lo normaliza."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .dji import run_parser, to_track
from .types import (
    FlightEvent,
    FlightLogError,
    FlightTrack,
    TrackPoint,
    build_summary,
)

DJI_NAME = re.compile(r"^(dji)?flightrecord.*\.txt$", re.IGNORECASE)

SYNTHETIC_NOTICE = "synthetic_example_data"


def _read_synthetic_json(path: Path):
    """El JSON si el archivo es uno sintético (`"synthetic": true`); si no, `None`."""
    if path.suffix.lower() != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("synthetic") is True:
        return data
    return None


class SyntheticAdapter:
    """Sólo para pruebas y demostración: lee un JSON etiquetado como sintético.

    Nunca se confunde con un log real: exige `"synthetic": true` y el resultado lleva la marca
    `synthetic`, que la pantalla muestra como «Synthetic example data».
    """

    name = "synthetic"

    def detect(self, path: Path) -> bool:
        return _read_synthetic_json(path) is not None

    def parse(self, path: Path, keychain_cache: Path | None = None) -> FlightTrack:
        data = _read_synthetic_json(path)
        try:
            points = [
                TrackPoint(
                    t=float(p["t"]),
                    lat=p.get("lat"),
                    lon=p.get("lon"),
                    height_m=p.get("height_m"),
                    speed_ms=p.get("speed_ms"),
                    battery_pct=p.get("battery_pct"),
                    satellites=p.get("satellites"),
                )
                for p in data.get("points", [])
            ]
            events = [
                FlightEvent(
                    t=float(e["t"]),
                    level=e.get("level", "info"),
                    code=e.get("code", ""),
                    raw_text=e.get("raw_text", ""),
                    explanation=e.get("explanation", ""),
                    inferred=bool(e.get("inferred", False)),
                )
                for e in data.get("events", [])
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise FlightLogError(
                FlightLogError.INCOMPLETE, "malformed synthetic points"
            ) from exc
        if sum(1 for p in points if p.lat is not None and p.lon is not None) < 2:
            raise FlightLogError(
                FlightLogError.INSUFFICIENT_DATA, "fewer than two positioned points"
            )
        return FlightTrack(
            points=points,
            events=events,
            summary=build_summary(points, data.get("started_at"), data.get("timezone")),
            uninterpreted=list(data.get("uninterpreted", [])),
            source_format="synthetic",
            limitations=[SYNTHETIC_NOTICE],
            synthetic=True,
        )


class DjiAdapter:
    """DJI `FlightRecord*.txt`, leído con el envoltorio `tools/dji-log-json` (ver `dji.py`).

    Sin `settings.DJI_LOG_PARSER_BIN` el error es `parser_unavailable`; sin clave de la API de
    DJI (y sin llaves en caché), `missing_api_key`. Con `keychain_cache` las llaves del log se
    guardan tras el primer pedido y la segunda lectura no necesita red.
    """

    name = "dji"

    def detect(self, path: Path) -> bool:
        return bool(DJI_NAME.match(path.name))

    def parse(self, path: Path, keychain_cache: Path | None = None) -> FlightTrack:
        return to_track(run_parser(path, keychain_cache))


ADAPTERS = (SyntheticAdapter(), DjiAdapter())
