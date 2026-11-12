"""LV-431: lo que la pantalla de análisis necesita cuando el log no cuelga de un permiso."""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.registry.models import normalize_serial


def back_link(analysis) -> dict:
    """Adónde vuelve el botón «Volver»: al permiso si lo hay; si no, a la lista de logs."""
    if analysis.permission_id:
        return {
            "url": reverse("permission-operations", args=[analysis.permission_id]),
            "label": _("Back to operations"),
        }
    return {"url": reverse("flight-log-list"), "label": _("Back to flight logs")}


# LV-434: el log DJI guarda la serie de la aeronave en un campo de 16 caracteres, así que una
# serie de 20 caracteres llega con sus primeros 16 (p. ej. «AAAA…» de 20 → sus 16 primeros). No es coincidencia
# aproximada: es el truncado del formato, y sólo se acepta con exactamente ese largo.
DJI_SERIAL_FIELD = 16


def same_serial(log_serial, registered) -> bool:
    log_serial, registered = normalize_serial(log_serial), normalize_serial(registered)
    if not log_serial or not registered:
        return False
    if log_serial == registered:
        return True
    return len(log_serial) == DJI_SERIAL_FIELD and registered.startswith(log_serial)


def serial_mismatch_warning(analysis, track) -> str:
    """Aviso si la serie que dice el log no es la de la aeronave elegida en el alta.

    Se guarda igual (el log es evidencia); sólo se avisa. Sin aeronave elegida o sin serie
    en el log no hay nada que comparar, y no se supone nada.
    """
    aircraft = analysis.aircraft
    log_serial = normalize_serial((track.aircraft or {}).get("serial"))
    if aircraft is None or not log_serial:
        return ""
    if same_serial(log_serial, aircraft.serial_number):
        return ""
    return _(
        "The serial in the log (%(log)s) does not match the selected aircraft (%(aircraft)s)."
    ) % {
        "log": log_serial,
        "aircraft": aircraft.serial_number or aircraft.registration,
    }
