"""LV-202: una circunferencia dibujada es una circunferencia para el backend.

Reportado por el usuario como **crítico**: *"necesito dibujar una circunferencia;
al momento de apretar el botón sólo genera un marker […] debo dibujar la
circunferencia y cuando se termine de editar y finalizar me cree un pin central"*.

El síntoma se explica solo con la configuración a la vista: el círculo estaba
apagado (`drawCircle: false`), así que el único botón redondo de la barra era el
de **punto** (`drawCircleMarker`, que es cómo se dibuja un KML Point). No fallaba
nada; no había herramienta de círculo.

Y encenderla no bastaba: `L.Circle.toGeoJSON()` devuelve un `Point` y **pierde el
radio**, así que lo dibujado habría llegado al documento sin la única cifra que
importa. Lo que la fila agrega es la conversión a **anillo cerrado
poligonalizado**, que es cómo llegan los círculos reales — los KMZ de Trimble
Business Center de CC 738, que `R10.4` aprendió a leer.

**Por qué estos tests están en Python y no en JS**: el repo no tiene infra de
tests de JavaScript, y lo que hay que proteger no es el dibujo sino el acuerdo
entre las dos mitades — que el anillo que el navegador produce sea el que
`estimate_radius_m` reconoce, con el radio que el usuario pidió. Eso se puede
afirmar exactamente replicando la fórmula acá y midiéndola con el código real del
servidor. Si alguien cambia `CIRCLE_SIDES` o el radio terrestre del JS y se
aparta del umbral, estos tests caen.
"""

import math
import re
from pathlib import Path

from django.conf import settings

from apps.geo.sections import MAX_RADIUS_DEVIATION, estimate_radius_m

# Latitudes reales de la operación: CC 738 (Los Pelambres) y las faenas del
# norte, que es donde se dibujan estos planes. La corrección por latitud es lo
# que más se aparta de la aproximación plana, así que se mide donde se usa.
LATITUDES = (-22.3, -24.25, -31.7, -33.4)
EDIT_JS = Path(settings.BASE_DIR) / "static" / "js" / "geo" / "edit.js"
DOC_JS = Path(settings.BASE_DIR) / "static" / "js" / "geo" / "doc.js"

EARTH_RADIUS_M = 6371008.8
DEG = math.pi / 180


def _circle_ring(lat, lon, radius_m, sides):
    """La misma fórmula que `circleRing` en `static/js/geo/doc.js`.

    Duplicada a propósito y no importada —no se puede, es otro lenguaje—: lo que
    estos tests afirman es que **esa** fórmula produce anillos que el servidor
    acepta. Si las dos se separan, el test deja de proteger nada, así que
    cualquier cambio en el JS tiene que llegar hasta acá.
    """
    meters_per_degree = EARTH_RADIUS_M * DEG
    d_lat = radius_m / meters_per_degree
    cos = math.cos(lat * DEG)
    d_lon = d_lat if abs(cos) < 1e-9 else radius_m / (meters_per_degree * cos)
    ring = []
    for index in range(sides):
        angle = 2 * math.pi * index / sides
        ring.append([lon + d_lon * math.cos(angle), lat + d_lat * math.sin(angle)])
    ring.append(list(ring[0]))
    return ring


def _sides_from_js():
    """`CIRCLE_SIDES` leído del módulo, para que el test siga al código."""
    match = re.search(r"CIRCLE_SIDES\s*=\s*(\d+)", DOC_JS.read_text(encoding="utf-8"))
    assert match, "CIRCLE_SIDES no está declarado en doc.js"
    return int(match.group(1))


class TestTheDrawnRingIsAcceptedAsACircle:
    def test_the_measured_radius_is_the_one_that_was_drawn(self):
        """La cifra que se copia a la casilla "Radio (m)" del formulario de SIGO
        tiene que ser la que el usuario dibujó. Se acepta 0.5% de margen: el
        anillo es un polígono inscrito, así que su radio medio es por
        construcción algo menor que el del círculo."""
        sides = _sides_from_js()
        for lat in LATITUDES:
            for radius in (252.0, 1000.0, 2396.0, 3115.0):
                ring = _circle_ring(lat, -70.0, radius, sides)
                measured, _deviation = estimate_radius_m((lat, -70.0), ring)

                assert abs(measured - radius) / radius < 0.005, (lat, radius)

    def test_it_is_well_under_the_not_a_circle_threshold(self):
        """El umbral es 0.10 y el comentario de esa constante promete que "el
        círculo de 36 lados que dibujan las herramientas queda muy por debajo".
        Con la poligonalización de esta fila tiene que seguir siendo cierto, o el
        plan dibujado saldría marcado como "no es un círculo" y con una propuesta
        de círculo envolvente que no hace falta."""
        sides = _sides_from_js()
        for lat in LATITUDES:
            ring = _circle_ring(lat, -70.0, 1000.0, sides)

            _measured, deviation = estimate_radius_m((lat, -70.0), ring)

            assert deviation < MAX_RADIUS_DEVIATION / 5, (lat, deviation)

    def test_the_ring_is_closed(self):
        """`closed_ring_of` sólo acepta el anillo si el último vértice repite el
        primero, y de eso depende que el círculo dibujado se lea como área."""
        ring = _circle_ring(-24.25, -70.0, 1000.0, _sides_from_js())

        assert ring[0] == ring[-1]

    def test_enough_sides_that_a_rectangle_could_not_pass_for_this(self):
        """El contraejemplo que `estimate_radius_m` documenta: las cuatro esquinas
        de un rectángulo equidistan de su centro. Con pocos lados, un anillo
        "circular" se acercaría a ese caso degenerado; el número declarado en el
        JS tiene que quedar del lado seguro."""
        assert _sides_from_js() >= 36


class TestTheToolbarOffersIt:
    """Se lee **el archivo**, igual que el test de iconos de `R10.3` y el del
    botón retirado de `LV-131`: no hay infra de tests de JS, y lo que se afirma es
    que la herramienta quedó declarada — que es exactamente lo que faltaba.
    """

    def test_the_circle_tool_is_on(self):
        assert re.search(r"drawCircle:\s*true", EDIT_JS.read_text(encoding="utf-8"))

    def test_the_point_tool_is_still_on(self):
        """`drawCircleMarker` **es** la herramienta de puntos (KML Point), no un
        círculo a medias: apagarla al agregar el círculo habría quitado la forma
        de dibujar un punto, que es justo lo que el usuario sí podía hacer."""
        assert re.search(
            r"drawCircleMarker:\s*true", EDIT_JS.read_text(encoding="utf-8")
        )

    def test_the_center_pin_is_named_from_the_server(self):
        """El rótulo viaja en `config.labels`, como el resto: en estos módulos no
        se escriben cadenas visibles porque no habría cómo traducirlas."""
        assert "labels.circleCenter" in EDIT_JS.read_text(encoding="utf-8")
