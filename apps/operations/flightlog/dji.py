"""LV-429: lector de logs DJI real.

Invoca el envoltorio `tools/dji-log-json` (crate `dji-log-parser`, MIT) y traduce su JSON a
`FlightTrack`. Nunca se inventa nada: lo que el log no trae queda en `None`. La clave de la API de
DJI viaja sólo por el entorno del proceso hijo y jamás se escribe en un log ni en un mensaje.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess  # nosec B404 - se invoca un binario propio con lista de argumentos, sin shell
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings

from .types import (
    FlightEvent,
    FlightLogError,
    FlightTrack,
    TrackPoint,
    build_summary,
)

logger = logging.getLogger(__name__)

TIMEOUT_S = 120
LOCAL_TZ = "America/Santiago"
# Variables que el proceso hijo necesita para arrancar; el resto del entorno no se le pasa.
_INHERITED_ENV = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG")
# Estados de `goHomeStatus` que cuentan como regreso automático en curso.
_RETURNING = {"navigating", "gotohome", "goinghome", "returning"}

_ERROR_CODES = {
    "unsupported_format": FlightLogError.UNSUPPORTED_FORMAT,
    "missing_api_key": FlightLogError.MISSING_API_KEY,
    "keychain_error": FlightLogError.KEYCHAIN_ERROR,
    "incomplete": FlightLogError.INCOMPLETE,
    "read_error": FlightLogError.INCOMPLETE,
    "usage": FlightLogError.INCOMPLETE,
}

# Clasificación de los textos que la app del piloto muestra (en su idioma): español e inglés.
_TEXT_RULES = (
    ("low_battery_rth", re.compile(r"\b(rpo|rth)\b")),
    (
        "altitude_zone",
        re.compile(r"altitude (zone|limit)|zona de altitud|l[ií]mite de altitud"),
    ),
    (
        "gimbal_limit",
        re.compile(
            r"(gimbal|estabilizador).*(limit|l[ií]mite)|(limit|l[ií]mite).*(gimbal|estabilizador)"
        ),
    ),
)


def _env() -> dict:
    env = {k: os.environ[k] for k in _INHERITED_ENV if k in os.environ}
    key = (getattr(settings, "DJI_API_KEY", "") or "").strip()
    if key:
        env["DJI_API_KEY"] = key
    return env


def _scrub(text: str) -> str:
    """Quita la clave de un texto que va a un mensaje de error (por si el CLI la repitiera)."""
    key = (getattr(settings, "DJI_API_KEY", "") or "").strip()
    return text.replace(key, "***") if key else text


def run_parser(path: Path, keychain_cache: Path | None = None) -> dict:
    """Corre el binario y devuelve su JSON; traduce sus fallos a `FlightLogError`."""
    binary = (getattr(settings, "DJI_LOG_PARSER_BIN", "") or "").strip()
    if not binary:
        raise FlightLogError(
            FlightLogError.PARSER_UNAVAILABLE, "no DJI log reader is configured"
        )
    command = [binary, str(path)]
    if keychain_cache is not None:
        command += ["--keychains", str(keychain_cache)]
    try:
        done = subprocess.run(  # nosec B603 - lista de argumentos, sin shell, binario configurado
            command,
            capture_output=True,
            timeout=TIMEOUT_S,
            env=_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FlightLogError(
            FlightLogError.INCOMPLETE, "the DJI log reader took too long"
        ) from exc
    except OSError as exc:
        raise FlightLogError(
            FlightLogError.PARSER_UNAVAILABLE, "the DJI log reader could not be started"
        ) from exc
    if done.returncode != 0:
        raise _error_from_stderr(done.stderr)
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        raise FlightLogError(
            FlightLogError.INCOMPLETE, "the DJI log reader returned unreadable output"
        ) from exc


def _error_from_stderr(stderr: bytes | str) -> FlightLogError:
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in reversed(text.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and "error" in data:
            code = _ERROR_CODES.get(str(data["error"]), FlightLogError.INCOMPLETE)
            return FlightLogError(code, _scrub(str(data.get("message", "")))[:300])
    return FlightLogError(FlightLogError.INCOMPLETE, "the DJI log reader failed")


def readable_model(product_type: str | None) -> str | None:
    """`Mavic3Enterprise` -> `Mavic 3 Enterprise`."""
    if not product_type:
        return None
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", " ", product_type)


def _number(value):
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _position(osd: dict):
    lat, lon = _number(osd.get("latitude")), _number(osd.get("longitude"))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None, None
    if abs(lat) > 90 or abs(lon) > 180:
        return None, None
    return lat, lon


def _points(frames: list) -> list[TrackPoint]:
    points = []
    for frame in frames:
        osd = (frame or {}).get("osd") or {}
        t = _number(osd.get("flyTime"))
        if t is None:
            continue
        lat, lon = _position(osd)
        xs, ys = _number(osd.get("xSpeed")), _number(osd.get("ySpeed"))
        battery = _number(((frame.get("battery") or {}).get("chargeLevel")))
        sats = _number(osd.get("gpsNum"))
        points.append(
            TrackPoint(
                t=float(t),
                lat=lat,
                lon=lon,
                height_m=_number(osd.get("height")),
                speed_ms=None if xs is None or ys is None else math.hypot(xs, ys),
                battery_pct=battery,
                satellites=None if sats is None else int(sats),
            )
        )
    return points


def _classify(text: str) -> str:
    lowered = text.lower()
    for code, rule in _TEXT_RULES:
        if rule.search(lowered):
            return code
    return ""


def _app_items(frame: dict):
    app = frame.get("app") or {}
    for kind in ("warn", "tip"):
        value = app.get(kind)
        if not isinstance(value, str):
            continue
        for part in re.split(r";\s*", value):
            part = part.strip()
            if part:
                yield kind, part


def _events(frames: list):
    """Eventos y tramo de regreso. Un texto del log da un evento por **aparición nueva**: no se
    repite mientras siga presente en los cuadros consecutivos."""
    events: list[FlightEvent] = []
    previous_items: set = set()
    previous_mode = None
    previous_returning = False
    return_start = None
    last_t = None
    for frame in frames:
        osd = (frame or {}).get("osd") or {}
        t = _number(osd.get("flyTime"))
        if t is None:
            continue
        last_t = float(t)
        items = set(_app_items(frame))
        for kind, text in sorted(items - previous_items):
            code = _classify(text)
            events.append(
                FlightEvent(
                    t=last_t,
                    level="warning" if kind == "warn" else "info",
                    code=f"{kind}:{code}" if code else kind,
                    raw_text=text,
                    explanation="",
                )
            )
        previous_items = items
        mode = osd.get("flycState")
        if isinstance(mode, str) and mode != previous_mode:
            events.append(
                FlightEvent(
                    t=last_t,
                    level="info",
                    code=f"mode:{mode}",
                    raw_text=f"flycState: {mode}",
                    explanation="",
                )
            )
            previous_mode = mode
        status = osd.get("goHomeStatus")
        returning = isinstance(status, str) and status.lower() in _RETURNING
        if returning and not previous_returning and mode != "GoHome":
            events.append(
                FlightEvent(
                    t=last_t,
                    level="info",
                    code="auto_return_status",
                    raw_text=f"goHomeStatus: {status}",
                    explanation="",
                )
            )
        previous_returning = returning
        if return_start is None and (mode == "GoHome" or returning):
            return_start = last_t
    leg = None if return_start is None or last_t is None else [return_start, last_t]
    return events, leg


def _started_at(raw):
    if not isinstance(raw, str):
        return None, None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (
        moment.astimezone(ZoneInfo(LOCAL_TZ)).isoformat(timespec="seconds"),
        moment.astimezone(UTC).isoformat(timespec="seconds"),
    )


def to_track(data: dict) -> FlightTrack:
    """El JSON del envoltorio (`details` + `frames`) como `FlightTrack`."""
    if not isinstance(data, dict) or not isinstance(data.get("frames"), list):
        raise FlightLogError(FlightLogError.INCOMPLETE, "the log has no frames")
    frames = [f for f in data["frames"] if isinstance(f, dict)]
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    points = _points(frames)
    if sum(1 for p in points if p.lat is not None) < 2:
        raise FlightLogError(
            FlightLogError.INSUFFICIENT_DATA, "fewer than two positioned points"
        )
    local, utc = _started_at(details.get("startTime"))
    summary = build_summary(points, local, LOCAL_TZ if local else None)
    summary.started_at_utc = utc
    # `details` trae la distancia en **km**; el resumen la guarda en metros.
    total_km = _number(details.get("totalDistance"))
    if total_km is not None:
        summary.distance_m = round(total_km * 1000, 1)
    total_time = _number(details.get("totalTime"))
    if total_time is not None:
        summary.duration_s = round(float(total_time), 1)
    events, leg = _events(frames)
    serial = details.get("aircraftSn")
    aircraft = {
        "log_model": readable_model(details.get("productType")),
        "serial": serial.strip()
        if isinstance(serial, str) and serial.strip()
        else None,
    }
    return FlightTrack(
        points=points,
        events=events,
        summary=summary,
        uninterpreted=[],
        source_format="dji",
        aircraft=aircraft,
        return_leg=leg,
    )
