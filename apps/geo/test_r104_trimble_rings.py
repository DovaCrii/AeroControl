"""R10.4: la circunferencia también llega como `LineString` cerrado.

Los KMZ que el usuario aportó el 2026-08-24 para los permisos de CC 738 —siete
archivos `CG-0N_circunferencia_grande.kmz`— los exporta **Trimble Business
Center**, y ahí el círculo no es un `Polygon`: es un `LineString` cerrado de
cientos de vértices (251 a 770 en los reales) acompañado de su punto "Centro
CG-0N". Mirando sólo `Polygon`, `split_sections` devolvía las siete secciones
con `no_circle` y sin radio: la app decía "sin círculo" sobre archivos que
traían el círculo dibujado, y el flujo entero —radio, AMC, distancia, las
casillas de SIGO— quedaba vacío.

Los fixtures reproducen esa forma, no la de MLP (que ya cubre
`test_r91_sections.py`): un solo par en la raíz, el anillo como `LineString`, y
los radios y conteos de vértices del orden de los archivos reales.
"""

import math

from apps.geo.kml.canonical import empty_document, new_uid, validate_document
from apps.geo.sections import (
    MAX_RADIUS_DEVIATION,
    WARNING_NO_CENTER_POINT,
    WARNING_NOT_A_CIRCLE,
    build_section_document,
    closed_ring_of,
    split_sections,
)

# Centro real de "CG-01 | Circunferencia grande | Quebrada km 13.760".
LAT, LON = -31.906392, -70.717982
RADIUS_M = 2018  # el medido en el archivo real, redondeado


def _placemark(name, geometry):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": geometry,
        "extended_data": None,
        "extras": [],
    }


def _ring_coords(lat, lon, radius_m, vertices=180, close=True):
    ring = []
    for step in range(vertices):
        angle = 2 * math.pi * step / vertices
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    if close:
        ring.append(list(ring[0]))
    return ring


def _trimble_like_document(radius_m=RADIUS_M, close=True):
    """La forma de Trimble: el anillo como `LineString` y su punto centro."""
    document = empty_document()
    document["children"].append(
        _placemark(
            "CG-01 | Circunferencia grande | Quebrada km 13.760",
            {
                "type": "LineString",
                "coordinates": _ring_coords(LAT, LON, radius_m, close=close),
            },
        )
    )
    document["children"].append(
        _placemark("Centro CG-01", {"type": "Point", "coordinates": [LON, LAT, 0]})
    )
    return document


class TestTheTrimbleShape:
    def test_a_closed_linestring_is_the_circle_of_its_point(self):
        sections = split_sections(_trimble_like_document())

        assert len(sections) == 1
        section = sections[0]
        assert section.name == "Centro CG-01"
        assert section.warnings == []
        assert section.circle is not None
        # El radio medido contra el punto declarado, no el centroide del anillo.
        assert abs(section.radius_m - RADIUS_M) < 5
        assert section.radius_deviation < MAX_RADIUS_DEVIATION

    def test_the_center_is_the_declared_point(self):
        sections = split_sections(_trimble_like_document())

        assert sections[0].center == (LAT, LON)

    def test_the_exported_section_keeps_the_ring(self):
        """El KMZ de sección que se sube a SIGO debe llevar el círculo.

        `build_section_document` copia la geometría tal cual, así que un anillo
        `LineString` tiene que sobrevivir el viaje y volver a medirse igual.
        """
        section = split_sections(_trimble_like_document())[0]

        document = build_section_document(section)
        validate_document(document)
        types = [child["geometry"]["type"] for child in document["children"]]
        assert types == ["Point", "LineString"]
        assert split_sections(document)[0].radius_m == section.radius_m


class TestWhatMustNotBecomeACircle:
    def test_an_open_linestring_is_a_path_and_is_ignored(self):
        """Un trazado abierto —un camino, una quebrada— no encierra nada.

        Tomarlo por área convertiría una ruta en una circunferencia de vuelo, y
        el punto se quedaría sin círculo: es lo correcto, y así se informa.
        """
        document = _trimble_like_document(close=False)

        sections = split_sections(document)

        assert len(sections) == 1
        assert sections[0].warnings == ["no_circle"]
        assert sections[0].radius_m is None

    def test_a_closed_ring_that_is_not_round_is_flagged(self):
        """Cerrado no es lo mismo que circular: el umbral sigue mandando."""
        document = empty_document()
        square = [
            [LON - 0.01, LAT - 0.01, 0],
            [LON + 0.01, LAT - 0.01, 0],
            [LON + 0.01, LAT + 0.01, 0],
            [LON - 0.01, LAT + 0.01, 0],
        ]
        square.append(list(square[0]))
        document["children"].append(
            _placemark("Perímetro", {"type": "LineString", "coordinates": square})
        )

        sections = split_sections(document)

        assert len(sections) == 1
        assert WARNING_NOT_A_CIRCLE in sections[0].warnings
        assert WARNING_NO_CENTER_POINT in sections[0].warnings

    def test_a_two_vertex_linestring_is_not_a_ring(self):
        """Ida y vuelta entre dos puntos: cerrado, pero sin área."""
        segment = [[LON, LAT, 0], [LON + 0.001, LAT, 0], [LON, LAT, 0]]

        assert (
            closed_ring_of(
                _placemark(
                    "Ida y vuelta", {"type": "LineString", "coordinates": segment}
                )
            )
            is None
        )
