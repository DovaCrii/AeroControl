"""LV-427: adaptadores de formato. Cada uno decide si reconoce el archivo y lo normaliza."""

from __future__ import annotations

import json
import re
from pathlib import Path

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

    def parse(self, path: Path) -> FlightTrack:
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
    """DJI `FlightRecord*.txt`: reconocido por el nombre, **todavía sin lector real**.

    TODO fase 2: invocar el CLI `dji-log-parser` (MIT) con `subprocess.run([...], shell=False)`,
    ruta en `settings.DJI_LOG_PARSER_BIN` y clave de la API de DJI en la variable de entorno
    `DJI_API_KEY` (sin ella: `missing_api_key`; sin el binario: `parser_unavailable`). Nunca
    escribir la clave en logs ni en mensajes de error. La salida JSON del CLI se traduce a
    `TrackPoint`/`FlightEvent`, dejando en `uninterpreted` lo que no se sepa explicar.
    """

    name = "dji"

    def detect(self, path: Path) -> bool:
        return bool(DJI_NAME.match(path.name))

    def parse(self, path: Path) -> FlightTrack:
        raise FlightLogError(
            FlightLogError.PARSER_UNAVAILABLE,
            "the DJI log reader is not connected yet",
        )


ADAPTERS = (SyntheticAdapter(), DjiAdapter())
