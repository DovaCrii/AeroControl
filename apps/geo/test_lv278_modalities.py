"""LV-278 (A-2): el motor de secciones reconoce las cuatro modalidades de SIGO.

SIGO ahora admite cuatro formas de declarar el área de vuelo: Punto Centro,
Punto Corredor, Triangular y Cuadricular. Hasta acá el motor sólo conocía la
primera: un triángulo o un cuadrilátero se volvía «el círculo que lo encierra»
(`not_a_circle` + `enclosing`) y una línea abierta se **descartaba sin aviso**.

Respuestas del usuario (2026-10-06): los vértices van en **sentido horario**, una
solicitud por área, y **toda área genera un punto central** desde el que se
calcula la distancia al aeródromo.
"""

import math

import pytest

from apps.geo.kml.build import build_kml_bytes
from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.sections import (
    MODALITY_CENTER_POINT,
    MODALITY_CORRIDOR,
    MODALITY_QUADRILATERAL,
    MODALITY_TRIANGLE,
    WARNING_NO_CENTER_POINT,
    WARNING_NOT_A_CIRCLE,
    build_section_document,
    split_sections,
)

LAT, LON = -22.3, -68.9
# Grados por metro, para armar figuras con medidas reales.
M_LAT = 1 / 111_320
M_LON = 1 / (111_320 * math.cos(math.radians(LAT)))


def _at(east_m, north_m):
    return [LON + east_m * M_LON, LAT + north_m * M_LAT]


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


def _document(*placemarks):
    document = empty_document()
    document["children"].extend(placemarks)
    return document


def _polygon(name, points):
    ring = [*points, points[0]]
    return _placemark(name, {"type": "Polygon", "coordinates": [ring]})


def _closed_line(name, points):
    """Como lo exporta Trimble: un `LineString` cerrado en vez de un `Polygon`."""
    return _placemark(name, {"type": "LineString", "coordinates": [*points, points[0]]})


def _line(name, points):
    return _placemark(name, {"type": "LineString", "coordinates": points})


def _point(name, east_m, north_m):
    return _placemark(name, {"type": "Point", "coordinates": _at(east_m, north_m)})


def _circle(name, radius_m, sides=64):
    return _polygon(
        name,
        [
            _at(
                radius_m * math.cos(2 * math.pi * i / sides),
                radius_m * math.sin(2 * math.pi * i / sides),
            )
            for i in range(sides)
        ],
    )


# Dos vueltas del mismo triángulo: la lista de abajo es antihoraria (norte-este-oeste
# visto desde arriba) y su inversa es horaria.
TRIANGLE_CCW = [_at(0, 0), _at(200, 0), _at(100, 150)]
SQUARE_CCW = [_at(0, 0), _at(200, 0), _at(200, 200), _at(0, 200)]


def _signed_area(vertices):
    """Positivo = antihorario (x al este, y al norte)."""
    total = 0.0
    for index, (x1, y1) in enumerate(vertices):
        x2, y2 = vertices[(index + 1) % len(vertices)]
        total += x1 * y2 - x2 * y1
    return total / 2


class TestPolygons:
    def test_three_vertices_are_a_triangle_not_an_enclosing_circle(self):
        (section,) = split_sections(_document(_polygon("T", TRIANGLE_CCW)))

        assert section.modality == MODALITY_TRIANGLE
        assert section.enclosing is None
        assert section.radius_m is None
        assert WARNING_NOT_A_CIRCLE not in section.warnings
        assert len(section.vertices) == 3

    def test_four_vertices_are_a_quadrilateral(self):
        (section,) = split_sections(_document(_polygon("Q", SQUARE_CCW)))

        assert section.modality == MODALITY_QUADRILATERAL
        assert section.enclosing is None
        assert len(section.vertices) == 4

    def test_a_trimble_closed_line_with_three_vertices_is_a_triangle_too(self):
        (section,) = split_sections(_document(_closed_line("T", TRIANGLE_CCW)))

        assert section.modality == MODALITY_TRIANGLE

    @pytest.mark.parametrize("ring", [TRIANGLE_CCW, SQUARE_CCW])
    def test_vertices_come_out_clockwise_whichever_way_they_were_drawn(self, ring):
        for drawn in (ring, ring[::-1]):
            (section,) = split_sections(_document(_polygon("A", drawn)))

            assert _signed_area(section.vertices) < 0, "debe ser horario"
            # Sin repetir el vértice de cierre.
            assert section.vertices[0] != section.vertices[-1]

    def test_without_a_drawn_point_the_centre_is_the_area_centroid(self):
        (section,) = split_sections(_document(_polygon("Q", SQUARE_CCW)))

        lat, lon = section.center
        expected = _at(100, 100)
        assert lat == pytest.approx(expected[1], abs=1e-6)
        assert lon == pytest.approx(expected[0], abs=1e-6)

    def test_the_centroid_is_the_area_one_not_the_vertex_mean(self):
        """Cuatro vértices con tres de ellos juntos: la media de vértices cae
        hacia ese lado y el centroide del área no."""
        skewed = [_at(0, 0), _at(10, 0), _at(20, 0), _at(0, 100)]
        (section,) = split_sections(_document(_polygon("S", skewed)))
        vertex_mean_lon = sum(v[0] for v in skewed) / 4

        assert section.center[1] != pytest.approx(vertex_mean_lon, abs=1e-9)

    def test_a_missing_centre_point_is_not_an_error_for_these_shapes(self):
        (section,) = split_sections(_document(_polygon("T", TRIANGLE_CCW)))

        assert WARNING_NO_CENTER_POINT not in section.warnings
        assert section.warnings == []

    def test_a_drawn_point_inside_is_respected_as_the_declared_centre(self):
        document = _document(_polygon("T", TRIANGLE_CCW), _point("C", 100, 40))

        sections = split_sections(document)

        assert len(sections) == 1, "el punto se emparejó, no quedó suelto"
        assert sections[0].modality == MODALITY_TRIANGLE
        assert sections[0].center == pytest.approx((_at(100, 40)[1], _at(100, 40)[0]))
        assert sections[0].point is not None

    def test_five_or_more_irregular_vertices_still_get_the_enclosing_circle(self):
        pentagon = [_at(0, 0), _at(300, 0), _at(300, 50), _at(150, 90), _at(0, 50)]

        (section,) = split_sections(_document(_polygon("P", pentagon)))

        assert section.modality == MODALITY_CENTER_POINT
        assert WARNING_NOT_A_CIRCLE in section.warnings
        assert section.enclosing is not None

    def test_a_circle_is_still_a_centre_point(self):
        document = _document(_circle("Circulo", 200), _point("Centro", 0, 0))

        (section,) = split_sections(document)

        assert section.modality == MODALITY_CENTER_POINT
        assert section.radius_m == pytest.approx(200, abs=3)
        assert section.vertices == []


class TestCorridors:
    AXIS = [_at(0, 0), _at(100, 0), _at(100, 300)]

    def test_an_open_line_is_a_corridor_and_no_longer_vanishes(self):
        sections = split_sections(_document(_line("Camino", self.AXIS)))

        assert len(sections) == 1
        assert sections[0].modality == MODALITY_CORRIDOR

    def test_the_axis_keeps_the_order_it_was_drawn_in(self):
        """Es un eje, no un anillo: invertirlo cambiaría el sentido del corredor."""
        (section,) = split_sections(_document(_line("Camino", self.AXIS)))

        assert section.vertices == self.AXIS

    def test_the_centre_is_the_midpoint_along_the_axis(self):
        """A medio camino por **longitud**, no la media de vértices: con vértices
        desparejos (acá dos en el primer tramo) la media se corre hacia ellos."""
        axis = [_at(0, 0), _at(100, 0), _at(100, 300)]  # largo total 400 m

        (section,) = split_sections(_document(_line("Camino", axis)))

        lat, lon = section.center
        # A 200 m del inicio: 100 m al este y 100 m al norte.
        expected = _at(100, 100)
        assert lat == pytest.approx(expected[1], abs=2e-6)
        assert lon == pytest.approx(expected[0], abs=2e-6)
        assert section.radius_m is None
        assert section.warnings == []

    def test_a_point_near_the_midpoint_is_its_centre(self):
        document = _document(_line("Camino", self.AXIS), _point("Centro", 100, 100))

        sections = split_sections(document)

        assert len(sections) == 1
        assert sections[0].point is not None

    def test_a_two_point_line_is_still_a_corridor(self):
        (section,) = split_sections(_document(_line("Recta", [_at(0, 0), _at(500, 0)])))

        assert section.modality == MODALITY_CORRIDOR
        assert len(section.vertices) == 2


def test_a_mixed_plan_yields_one_section_per_area_in_each_modality():
    document = _document(
        _circle("Circulo", 150),
        _point("Centro", 0, 0),
        _polygon("Tri", [_at(2000, 0), _at(2200, 0), _at(2100, 150)]),
        _polygon("Cuad", [_at(4000, 0), _at(4200, 0), _at(4200, 200), _at(4000, 200)]),
        _line("Corr", [_at(6000, 0), _at(6400, 0)]),
    )

    modalities = sorted(section.modality for section in split_sections(document))

    assert modalities == sorted(
        [
            MODALITY_CENTER_POINT,
            MODALITY_TRIANGLE,
            MODALITY_QUADRILATERAL,
            MODALITY_CORRIDOR,
        ]
    )


class TestTheSectionKmz:
    def test_an_area_without_a_drawn_point_still_ships_its_centre(self):
        """SIGO pide el punto central con el área. Si el usuario no lo dibujó, el
        KMZ de la sección lo lleva igual (el centro calculado)."""
        (section,) = split_sections(_document(_polygon("Tri", TRIANGLE_CCW)))

        document = build_section_document(section)
        geometries = [c["geometry"]["type"] for c in document["children"]]

        assert sorted(geometries) == ["Point", "Polygon"]
        kml = build_kml_bytes(document)
        assert b"<Point>" in kml

    def test_a_circle_without_a_point_keeps_its_old_behaviour(self):
        """El círculo huérfano ya avisa `no_center_point`; no se le inventa uno."""
        (section,) = split_sections(_document(_circle("Circulo", 150)))

        document = build_section_document(section)

        assert [c["geometry"]["type"] for c in document["children"]] == ["Polygon"]
