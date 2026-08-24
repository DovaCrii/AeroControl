"""R10.8: la circunferencia mínima que encierra un área irregular.

El barrido de los KMZ vigentes del 2026-08-24 dejó el patrón a la vista: los
siete de CC 738 y los de CC 691 y CC 664 son círculos limpios, pero **CC 716,
CC 861 (×2), PMCHS y Caren son polígonos a mano alzada**. SIGO acepta una
circunferencia por solicitud, así que para esos cinco la app detectaba el
problema y dejaba el trabajo —sacar centro y radio— en Google Earth.

Estos tests fijan las dos propiedades de las que depende que el número sirva:
que **encierre todo** (si no, parte de la faena queda fuera de lo autorizado) y
que sea **mínimo** (si no, se pide más espacio aéreo del necesario, que es lo
que la DGAC evalúa). La geometría se prueba en el plano, sin latitudes de por
medio, y aparte se comprueba el viaje de ida y vuelta a coordenadas.
"""

import math

from apps.geo.enclosing import (
    enclosing_circle_of_ring,
    smallest_enclosing_circle,
)
from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.sections import WARNING_NOT_A_CIRCLE, split_sections

# Un punto del área real de CC 861, para que los órdenes de magnitud sean los
# del caso que motivó la fila (radios equivalentes de kilómetros).
LAT, LON = -22.329039, -68.791275


def _naive_radius(points):
    """Lo que daría "centroide más distancia al punto más lejano".

    Es la implementación de tres líneas que este módulo decidió **no** usar, y
    está acá para poder medir cuánto se pasa en vez de afirmarlo.
    """
    cx = sum(x for x, _y in points) / len(points)
    cy = sum(y for _x, y in points) / len(points)
    return max(math.hypot(x - cx, y - cy) for x, y in points)


class TestTheGeometry:
    def test_a_square_gets_its_circumscribed_circle(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]

        x, y, radius = smallest_enclosing_circle(square)

        assert (x, y) == (5, 5)
        # La mitad de la diagonal: 10·√2/2.
        assert radius == math.sqrt(200) / 2

    def test_a_flat_triangle_uses_its_longest_side_not_its_circumcircle(self):
        """El caso que delata una implementación ingenua.

        En un triángulo **obtuso** la circunferencia que pasa por los tres
        vértices no es la mínima: acá mide 13 y la mínima mide 5, porque el
        vértice de arriba ya cae dentro del círculo que tiene la base por
        diámetro.
        """
        triangle = [(0, 0), (10, 0), (5, 1)]

        x, y, radius = smallest_enclosing_circle(triangle)

        assert (round(x, 6), round(y, 6)) == (5, 0)
        assert radius == 5

    def test_it_beats_the_centroid_plus_farthest_vertex_by_a_third(self):
        """Sobre un área alargada la versión ingenua se pasa un 33%.

        Traducido al caso real: en el área de 12 km de CC 861 eso son kilómetros
        de radio pedidos de más a la DGAC.
        """
        elongated = [(0, 0), (100, 0), (0, 1)]

        _x, _y, radius = smallest_enclosing_circle(elongated)

        assert radius < _naive_radius(elongated) * 0.76
        # Apenas más que la mitad del lado largo: el vértice de arriba obliga a
        # crecer 2.5 mm sobre los 50, y nada más.
        assert 50.0 <= radius < 50.01

    def test_every_vertex_ends_up_inside(self):
        """La propiedad que no se puede negociar: lo que queda fuera del círculo
        queda fuera del permiso."""
        polygon = [
            (math.cos(i) * (50 + i * 7), math.sin(i * 1.7) * (30 + i * 3))
            for i in range(40)
        ]

        x, y, radius = smallest_enclosing_circle(polygon)

        for px, py in polygon:
            # Tolerancia de coma flotante, no de criterio: 1 µm sobre metros.
            assert math.hypot(px - x, py - y) <= radius + 1e-6

    def test_the_answer_does_not_move_between_runs(self):
        """Welzl aleatoriza el orden; la semilla es fija a propósito. Un número
        que alguien va a copiar en un formulario del Estado no puede cambiar de
        decimal entre dos visitas a la misma pantalla."""
        polygon = [(math.cos(i) * 40, math.sin(i) * 25) for i in range(30)]

        assert smallest_enclosing_circle(polygon) == smallest_enclosing_circle(polygon)

    def test_a_single_point_is_a_circle_of_no_radius(self):
        assert smallest_enclosing_circle([(3, 4)]) == (3, 4, 0.0)

    def test_no_points_is_no_circle(self):
        assert smallest_enclosing_circle([]) is None


class TestOnRealCoordinates:
    def _ring(self, points):
        return [[LON + dx, LAT + dy, 0] for dx, dy in points]

    def test_the_circle_comes_back_in_degrees_and_metres(self):
        # Un cuadrado de aproximadamente 0.02° de lado: kilómetros, la escala de
        # las áreas que motivaron esto.
        ring = self._ring([(0, 0), (0.02, 0), (0.02, 0.02), (0, 0.02)])

        latitude, longitude, radius_m = enclosing_circle_of_ring(ring)

        # El centro cae en el medio del cuadrado.
        assert round(latitude, 5) == round(LAT + 0.01, 5)
        assert round(longitude, 5) == round(LON + 0.01, 5)
        # Media diagonal de un cuadrado de ~2.06 km de lado (la longitud se
        # encoge por el coseno de la latitud): del orden de 1.5 km.
        assert 1_200 < radius_m < 1_800

    def test_a_circle_encloses_itself_and_nothing_more(self):
        """Sobre un anillo que **sí** es circular el resultado es el mismo
        círculo. No se muestra en pantalla en ese caso —sería ruido— pero que la
        aritmética sea consistente es lo que hace creíble al otro caso."""
        radius_m = 3_000
        ring = self._ring(
            [
                (
                    (radius_m * math.sin(2 * math.pi * step / 90))
                    / (111_320 * math.cos(math.radians(LAT))),
                    (radius_m * math.cos(2 * math.pi * step / 90)) / 111_320,
                )
                for step in range(90)
            ]
        )

        _latitude, _longitude, measured = enclosing_circle_of_ring(ring)

        assert abs(measured - radius_m) / radius_m < 0.01


class TestWhatTheSectionCarries:
    def _placemark(self, name, geometry):
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

    def _document(self, offsets):
        ring = [[LON + dx, LAT + dy, 0] for dx, dy in offsets]
        ring.append(list(ring[0]))
        document = empty_document()
        document["children"].append(
            self._placemark("Área", {"type": "Polygon", "coordinates": [ring]})
        )
        return document

    def test_an_irregular_area_carries_the_proposal_beside_the_warning(self):
        """El aviso y la salida van juntos: un aviso solo es lo que había antes.

        La forma es la del caso real -- un polígono alargado, sin punto centro,
        como los de CC 861 y PMCHS.
        """
        document = self._document([(0, 0), (0.05, 0), (0.05, 0.004), (0, 0.004)])

        section = split_sections(document)[0]

        assert WARNING_NOT_A_CIRCLE in section.warnings
        assert section.enclosing is not None
        _latitude, _longitude, radius_m = section.enclosing
        # El anillo mide ~5 km de largo, así que su círculo ronda los 2.5 km.
        assert 2_000 < radius_m < 3_000

    def test_a_proper_circle_carries_no_proposal(self):
        """Sobre un círculo la propuesta sería el círculo mismo: ruido en la
        pantalla y una segunda fila que invita a preguntarse qué la diferencia
        de la primera."""
        circle = [
            (
                (500 * math.sin(2 * math.pi * step / 60))
                / (111_320 * math.cos(math.radians(LAT))),
                (500 * math.cos(2 * math.pi * step / 60)) / 111_320,
            )
            for step in range(60)
        ]

        section = split_sections(self._document(circle))[0]

        assert WARNING_NOT_A_CIRCLE not in section.warnings
        assert section.enclosing is None
