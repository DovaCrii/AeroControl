"""LV-429: explicaciones en lenguaje claro de los eventos conocidos de un log DJI.

El adaptador guarda sólo el código; el texto se traduce al mostrarse, así que cambiar de idioma no
exige reanalizar. Lo que no está acá queda con su texto original y `inferred=False`.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

EXPLANATIONS = {
    "tip:low_battery_rth": _(
        "The remaining battery is only enough to fly back to the home point. "
        "The aircraft advises returning now."
    ),
    "warn:low_battery_rth": _(
        "The remaining battery is only enough to fly back to the home point. "
        "The aircraft advises returning now."
    ),
    "tip:altitude_zone": _("The aircraft reported an altitude zone or altitude limit."),
    "warn:altitude_zone": _(
        "The aircraft reported an altitude zone or altitude limit."
    ),
    "tip:gimbal_limit": _(
        "The camera stabilizer (gimbal) reached the end of its movement range."
    ),
    "warn:gimbal_limit": _(
        "The camera stabilizer (gimbal) reached the end of its movement range."
    ),
    "mode:GoHome": _("The aircraft switched to automatic return to the home point."),
    "mode:AutoTakeoff": _("The aircraft took off automatically."),
    "mode:AutoLanding": _("The aircraft started an automatic landing."),
    "mode:ConfirmLanding": _(
        "The aircraft stopped near the ground and waited for the landing to be confirmed."
    ),
    "mode:GPSAtti": _(
        "The flight controller reported the GPS attitude mode (GPSAtti), "
        "a position-assisted flight mode."
    ),
    "mode:EngineStart": _("The motors were started."),
    "auto_return_status": _("The return-to-home system reported that it was active."),
}

UNEXPLAINED = _(
    "No plain-language explanation for this entry; see the original log text."
)


def explain(code: str, stored: str = "") -> str:
    """El texto guardado (logs sintéticos) o, si no hay, el de `code`; si no, el aviso genérico."""
    if stored:
        return stored
    known = EXPLANATIONS.get(code)
    return str(known if known is not None else UNEXPLAINED)
