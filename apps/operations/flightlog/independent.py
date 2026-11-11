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


def serial_mismatch_warning(analysis, track) -> str:
    """Aviso si la serie que dice el log no es la de la aeronave elegida en el alta.

    Se guarda igual (el log es evidencia); sólo se avisa. Sin aeronave elegida o sin serie
    en el log no hay nada que comparar, y no se supone nada.
    """
    aircraft = analysis.aircraft
    log_serial = normalize_serial((track.aircraft or {}).get("serial"))
    if aircraft is None or not log_serial:
        return ""
    if normalize_serial(aircraft.serial_number) == log_serial:
        return ""
    return _(
        "The serial in the log (%(log)s) does not match the selected aircraft (%(aircraft)s)."
    ) % {
        "log": log_serial,
        "aircraft": aircraft.serial_number or aircraft.registration,
    }
