"""LV-433: el mapa del análisis fija la vista antes de agregar capas.

Con el primer log real en producción el análisis y el reporte mostraron «No se pudo dibujar el
mapa»: `flight-analysis.js` agregaba la trayectoria a un mapa sin centro, Leaflet difería las capas
y al llegar `fitBounds` las agregaba con el renderer sin límites (`_clipPoints` → `reading 'min'`).
El JS no tiene pruebas de navegador en el gate, así que se vigila el orden en el fuente.
"""

from pathlib import Path

from django.conf import settings

SCRIPT = Path(settings.BASE_DIR) / "static" / "js" / "flight-analysis.js"


def test_the_view_is_set_before_any_layer_is_added():
    source = SCRIPT.read_text(encoding="utf-8")
    init = source[source.index("function init()") :]
    first_view = init.index("map.fitBounds(")
    first_layer = min(
        init.index(call)
        for call in ("addTiles(", "drawArea(", "drawTrack(", "drawReturn(")
    )
    assert first_view < first_layer
