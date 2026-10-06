"""T1.4 (paso 1): que un fallo al escribir la auditoría se vea.

El middleware escribe el `AuditEvent` **después** de la respuesta y fuera de toda
transacción. Si la escritura falla, la mutación ya se confirmó y lo único que queda
es una línea `audit_write_failed` en el log —que nadie mira—: el mismo patrón de
«un aviso que no llega a nadie» que `AGENTS.md` ya cuenta varias veces.

Este módulo deja una **marca en disco** cuando eso pasa, y el centro de
administración la lee en su panel de situación. En disco y no en la base por una
razón concreta: el fallo que se quiere ver puede ser justamente el de la base, y una
marca guardada ahí fallaría por el mismo motivo. Un archivo lo ven todos los
procesos del servidor y sobrevive a un reinicio.

**No cambia el comportamiento**: sigue siendo *fail-open* (la mutación no se
revierte). Hacerlo *fail-closed* es el paso (2) de T1.4, detrás de
`AUDIT_FAIL_CLOSED` y apagado por defecto, y se decide cuando esto lleve una
semana en cero. Nada de acá puede, a su vez, romper la petición: toda función
atrapa lo suyo.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("aerocontrol.request")

MARKER_NAME = "audit_write_failed.json"


def _marker_path():
    return Path(settings.LOG_DIR) / MARKER_NAME


def record_failure(*, request_id, method, path, error):
    """Anota (o suma) un fallo de escritura de auditoría. Nunca lanza.

    Guarda cuántas veces ha pasado y los datos del último: es lo que alguien
    necesita para saber si fue una vez o es cada petición.
    """
    try:
        previous = last_failure() or {}
        payload = {
            "count": int(previous.get("count", 0)) + 1,
            "first_at": previous.get("first_at") or _now(),
            "last_at": _now(),
            "request_id": str(request_id),
            "method": method,
            "path": str(path)[:200],
            # El tipo y no el mensaje: el mensaje de un error de base puede traer
            # datos de la fila, y esto se muestra en una pantalla.
            "error": type(error).__name__,
        }
        target = _marker_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, target)
    except Exception:  # noqa: BLE001 - la marca no puede romper la petición
        logger.exception("audit_failure_marker_unwritable")


def last_failure():
    """El registro del último fallo (con su cuenta), o None si no hay ninguno."""
    try:
        return json.loads(_marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clear_failure():
    """Borra la marca. Devuelve True si había una."""
    try:
        _marker_path().unlink()
    except FileNotFoundError:
        return False
    return True


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
