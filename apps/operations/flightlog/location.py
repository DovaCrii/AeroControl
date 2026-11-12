"""LV-435: dónde despegó el vuelo (comuna, provincia y región), calculado al dibujar.

No se guarda nada: `apps.geo.administrative.locate` es una consulta offline sobre la capa de la
BCN. Es una referencia, no un dato legal: los límites comunales están simplificados (~111 m).
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from apps.geo.administrative import locate

from .types import FlightTrack


def flight_place(track: FlightTrack):
    """`{'comuna', 'provincia', 'region', 'code'}` del punto de despegue, o None (sin punto de
    despegue o fuera de las comunas mapeadas)."""
    take = track.summary.takeoff
    if not take:
        return None
    return locate(take[0], take[1])


def place_sentence(place) -> str:
    """La frase del reporte; lleva `%(…)s`, así que se traduce acá y no con `{% translate %}`."""
    if not place:
        return ""
    return _(
        "Took off in the commune of %(comuna)s (%(provincia)s province, %(region)s)."
    ) % {
        "comuna": place["comuna"],
        "provincia": place["provincia"],
        "region": place["region"],
    }


def place_note() -> str:
    return _(
        "Reference only: the commune comes from the simplified communal boundaries of the BCN "
        "(about 111 m), so near a boundary the neighbouring commune may appear. If the takeoff "
        "is outside the mapped communes, no location is shown."
    )
