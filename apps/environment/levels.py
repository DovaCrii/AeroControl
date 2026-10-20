"""Niveles comunes de la sección «Entorno» (LV-358): ● Info, ▲ Atención, ◆ Fuerte.

Un solo vocabulario para los eventos del tiempo, el estado del centelleo GNSS y, más adelante, la
frescura de la foto del mapa. El símbolo y el texto van siempre juntos: el color nunca es lo único
que distingue un nivel, y ningún nivel usa el rojo de «crítico» (esto informa, no decide).
"""

from django.utils.translation import gettext_lazy

# Nivel -> (símbolo, rótulo), de menor a mayor.
LEVEL_LABELS = {
    "info": ("●", gettext_lazy("Info")),
    "attention": ("▲", gettext_lazy("Attention")),
    "strong": ("◆", gettext_lazy("Strong")),
}

LEVEL_ORDER = tuple(LEVEL_LABELS)


def level_info(level):
    """`(símbolo, rótulo)` de `level`; un nivel desconocido cuenta como informativo."""
    return LEVEL_LABELS.get(level, LEVEL_LABELS["info"])


def highest(levels):
    """El mayor de `levels` (`"info"` si no hay ninguno o no se reconoce)."""
    known = [level for level in levels if level in LEVEL_ORDER]
    return max(known, key=LEVEL_ORDER.index) if known else "info"
