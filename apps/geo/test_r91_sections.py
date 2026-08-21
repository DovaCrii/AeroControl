"""R9.1: el motor de secciones SIGO, contra la estructura del KMZ real.

SIGO acepta una circunferencia con su punto central por solicitud; el KMZ real
de MLP trae 47 pares en carpetas separadas (`Puntos` / `Radios de 30 m`). Estos
tests reproducen esa estructura en sintético — dos carpetas hermanas, el punto
en una y su círculo en la otra, nombres sólo en los puntos — porque es la forma
exacta en que el emparejamiento por nombre fallaría y el de cercanía no.

Los avisos se afirman por código, nunca por frase: la pantalla redacta y
traduce, y un test que fija la redacción se rompe con el idioma (`LV-95`).
"""

import math

from apps.geo.kml.build import build_kml_bytes
from apps.geo.kml.canonical import empty_document, new_uid, validate_document
from apps.geo.kml.kmz import build_kmz, read_kmz
from apps.geo.kml.parse import parse_kml_bytes
from apps.geo.sections import (
    WARNING_DUPLICATE_CENTER,
    WARNING_NO_CENTER_POINT,
    WARNING_NO_CIRCLE,
    WARNING_NOT_A_CIRCLE,
    build_section_document,
    estimate_radius_m,
    format_dms,
    haversine_km,
    split_sections,
    to_dms,
)

# Centro real del KMZ de MLP ("Quebrada km 13.760").
LAT, LON = -31.89439167, -70.70220833


def _point(name, lat, lon):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": {"type": "Point", "coordinates": [lon, lat, 0]},
        "extended_data": None,
        "extras": [],
    }


def _ring(lat, lon, radius_m, vertices=36):
    """Circunferencia como la dibujan las herramientas: N vértices a radio fijo."""
    ring = []
    for step in range(vertices):
        angle = 2 * math.pi * step / vertices
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    ring.append(list(ring[0]))  # el KML repite el primer vértice al final
    return ring


def _circle(name, lat, lon, radius_m):
    placemark = _point(name, lat, lon)
    placemark["geometry"] = {
        "type": "Polygon",
        "coordinates": [_ring(lat, lon, radius_m)],
    }
    return placemark


def _folder(name, children):
    return {
        "kind": "folder",
        "uid": new_uid("folder"),
        "name": name,
        "description": "",
        "visibility": True,
        "children": children,
    }


def _mlp_like_document():
    """Dos secciones con la estructura del KMZ real: puntos con nombre en una
    carpeta, círculos sin nombre en la hermana."""
    document = empty_document()
    second_lat, second_lon = -31.89285000, -70.70973333  # "Quebrada km 14.508"
    document["children"].append(
        _folder(
            "Quebradas (2)",
            [
                _folder(
                    "Puntos",
                    [
                        _point("Quebrada km 13.760", LAT, LON),
                        _point("Quebrada km 14.508", second_lat, second_lon),
                    ],
                ),
                _folder(
                    "Radios de 30 m",
                    [
                        _circle("", LAT, LON, 30),
                        _circle("", second_lat, second_lon, 30),
                    ],
                ),
            ],
        )
    )
    return document


class TestSplitOnTheRealShape:
    def test_pairs_points_with_their_circles_across_folders(self):
        sections = split_sections(_mlp_like_document())

        assert [section.name for section in sections] == [
            "Quebrada km 13.760",
            "Quebrada km 14.508",
        ]
        for section in sections:
            assert section.warnings == []
            assert section.point is not None and section.circle is not None

    def test_the_radius_is_read_off_the_polygon(self):
        sections = split_sections(_mlp_like_document())

        for section in sections:
            # 30 m dibujados; la conversión grados↔metros del fixture y la
            # esfera del cálculo justifican la tolerancia, no más que eso.
            assert abs(section.radius_m - 30) < 1
            assert section.radius_deviation < 0.02

    def test_the_center_is_the_declared_point_not_the_centroid(self):
        sections = split_sections(_mlp_like_document())

        assert sections[0].center == (LAT, LON)


class TestWhatDoesNotPairCleanly:
    def test_a_point_without_a_circle_is_kept_and_flagged(self):
        document = empty_document()
        document["children"].append(_point("Solo punto", LAT, LON))

        sections = split_sections(document)

        assert len(sections) == 1
        assert sections[0].warnings == [WARNING_NO_CIRCLE]
        assert sections[0].radius_m is None

    def test_a_circle_without_a_point_uses_its_centroid_and_flags(self):
        document = empty_document()
        document["children"].append(_circle("Huérfano", LAT, LON, 30))

        sections = split_sections(document)

        assert len(sections) == 1
        assert WARNING_NO_CENTER_POINT in sections[0].warnings
        lat, lon = sections[0].center
        assert abs(lat - LAT) < 1e-4 and abs(lon - LON) < 1e-4
        assert abs(sections[0].radius_m - 30) < 1

    def test_a_far_away_circle_does_not_get_adopted(self):
        """Un círculo a 5 km del único punto no es su circunferencia: umbral
        proporcional al radio, no un abrazo al vecino más cercano."""
        document = empty_document()
        document["children"].append(_point("Punto", LAT, LON))
        document["children"].append(_circle("", LAT + 0.05, LON, 30))

        sections = split_sections(document)

        codes = sorted(code for section in sections for code in section.warnings)
        assert codes == [WARNING_NO_CENTER_POINT, WARNING_NO_CIRCLE]

    def test_a_rectangle_is_flagged_as_not_a_circle(self):
        document = empty_document()
        document["children"].append(_point("Punto", LAT, LON))
        rectangle = _point("", LAT, LON)
        rectangle["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [LON - 0.001, LAT - 0.0001, 0],
                    [LON + 0.001, LAT - 0.0001, 0],
                    [LON + 0.001, LAT + 0.0001, 0],
                    [LON - 0.001, LAT + 0.0001, 0],
                    [LON - 0.001, LAT - 0.0001, 0],
                ]
            ],
        }
        document["children"].append(rectangle)

        sections = split_sections(document)

        assert len(sections) == 1
        assert WARNING_NOT_A_CIRCLE in sections[0].warnings


class TestWhatTheRealFileTaught:
    """Los dos defectos que aparecieron al correr el motor contra el KMZ de MLP
    y no contra fixtures propios. Van juntos porque comparten la lección: el
    dato real trae formas que uno no inventa al escribir el test."""

    def test_two_points_on_the_same_spot_each_keep_their_circle(self):
        """El emparejamiento "cada círculo elige su punto más cercano" fallaba
        acá: los dos círculos elegían el mismo punto, uno perdía el reclamo y
        quedaba huérfano **con su punto gemelo al lado**. En el KMZ real esto
        pasa tres veces."""
        document = empty_document()
        document["children"].append(
            _folder(
                "Puntos",
                [
                    _point("Quebrada km 46.272", LAT, LON),
                    _point("Quebrada km 46.924", LAT, LON),
                ],
            )
        )
        document["children"].append(
            _folder(
                "Radios de 30 m",
                [_circle("", LAT, LON, 30), _circle("", LAT, LON, 30)],
            )
        )

        sections = split_sections(document)

        assert len(sections) == 2
        for section in sections:
            assert section.circle is not None
            assert WARNING_NO_CIRCLE not in section.warnings
            assert WARNING_NO_CENTER_POINT not in section.warnings

    def test_duplicate_centers_are_flagged_on_every_member(self):
        """`Quebrada km 46.272` y `46.924` son quebradas distintas —650 m según
        sus propios nombres— sobre las mismas coordenadas: una fila mal
        transcrita en la tabla de origen. El motor no puede saber cuál dice la
        verdad, así que marca **las dos** y lo arbitra la persona."""
        document = empty_document()
        document["children"].append(_point("Quebrada km 46.272", LAT, LON))
        document["children"].append(_point("Quebrada km 46.924", LAT, LON))

        sections = split_sections(document)

        for section in sections:
            assert WARNING_DUPLICATE_CENTER in section.warnings

    def test_distinct_centers_are_not_flagged(self):
        """El contrapeso: dos quebradas vecinas de verdad no son un duplicado.
        Sin esto, el aviso saldría en todo el archivo y dejaría de significar
        algo -- la misma lección que las alertas de `LV-118`."""
        document = _mlp_like_document()

        sections = split_sections(document)

        for section in sections:
            assert WARNING_DUPLICATE_CENTER not in section.warnings


class TestDmsForTheSigoBoxes:
    def test_the_real_center_in_sigo_boxes(self):
        dms = to_dms(LAT, "lat")

        assert (dms["degrees"], dms["minutes"], dms["hemisphere"]) == (31, 53, "S")
        assert abs(dms["seconds"] - 39.81) < 0.01

    def test_carry_never_produces_sixty_seconds(self):
        dms = to_dms(30.99999999, "lat")

        assert (dms["degrees"], dms["minutes"], dms["seconds"]) == (31, 0, 0.0)

    def test_axes_have_their_own_hemispheres(self):
        assert to_dms(LON, "lon")["hemisphere"] == "W"
        assert to_dms(18.5, "lon")["hemisphere"] == "E"
        assert to_dms(0, "lat")["hemisphere"] == "N"

    def test_format_reads_like_a_chart(self):
        assert format_dms(LAT, "lat") == "31° 53' 39.81\" S"


class TestDistances:
    def test_one_degree_of_latitude(self):
        # 1° de latitud ≈ 111.195 km sobre la esfera media: la referencia
        # externa clásica, independiente de esta implementación.
        assert abs(haversine_km(0, 0, 1, 0) - 111.195) < 0.01

    def test_radius_measures_against_any_center(self):
        ring = _ring(LAT, LON, 30)
        radius_m, deviation = estimate_radius_m((LAT, LON), ring)

        assert abs(radius_m - 30) < 1
        assert deviation < 0.02


class TestTheSectionKmz:
    def test_the_section_document_is_valid_and_minimal(self):
        section = split_sections(_mlp_like_document())[0]
        document = build_section_document(section)

        validate_document(document)
        assert len(document["children"]) == 2
        # Sin estilos ni fragmentos crudos del documento madre: la sección no
        # re-emite XML ajeno hacia un formulario del Estado.
        for child in document["children"]:
            assert child["extras"] == [] and child["extended_data"] is None

    def test_the_kmz_round_trips_through_our_own_reader(self):
        section = split_sections(_mlp_like_document())[0]
        kmz = build_kmz(build_kml_bytes(build_section_document(section)))

        kml_bytes, resources = read_kmz(kmz)
        reparsed = parse_kml_bytes(kml_bytes)
        names = [pm.get("name") for pm in _placemarks(reparsed)]

        assert resources == []
        assert names == ["Quebrada km 13.760", "Quebrada km 13.760"]

    def test_one_circle_one_point_exactly_what_sigo_demands(self):
        section = split_sections(_mlp_like_document())[1]
        kmz = build_kmz(build_kml_bytes(build_section_document(section)))

        kml_bytes, _resources = read_kmz(kmz)
        reparsed = parse_kml_bytes(kml_bytes)
        types = sorted(
            pm["geometry"]["type"] for pm in _placemarks(reparsed) if pm["geometry"]
        )

        assert types == ["Point", "Polygon"]
        assert len(kmz) < 20 * 1024 * 1024


def _placemarks(document):
    from apps.geo.kml.canonical import iter_placemarks

    return list(iter_placemarks(document))
