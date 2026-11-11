"""LV-427: lector de logs de vuelo. Interfaz común + adaptadores por fabricante."""

from __future__ import annotations

from pathlib import Path

from .adapters import ADAPTERS
from .types import MAX_POINTS, FlightLogError, FlightTrack

__all__ = ["FlightLogError", "FlightTrack", "MAX_POINTS", "parse_flight_log"]


def parse_flight_log(path, keychain_cache=None) -> FlightTrack:
    """Elige el adaptador que reconoce el archivo y devuelve su `FlightTrack`."""
    path = Path(path)
    if not path.is_file():
        raise FlightLogError(FlightLogError.INCOMPLETE, "the file does not exist")
    for adapter in ADAPTERS:
        if adapter.detect(path):
            return adapter.parse(path, keychain_cache=keychain_cache)
    raise FlightLogError(FlightLogError.UNSUPPORTED_FORMAT, "unrecognised log format")
