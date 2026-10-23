"""LV-367 (fase 6): pertenencia a una comuna o región con geometría pura (`geometry_intersects_rings`,
`features_in_area`). Se prueba con áreas y zonas sintéticas, sin el archivo de BCN ni la base."""

from apps.geo.airspace_geometry import features_in_area, geometry_intersects_rings


def square(x0, y0, x1, y1):
    """Anillo cerrado [lon, lat]."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def polygon(*rings):
    return {"type": "Polygon", "coordinates": list(rings)}


def feature(kind, geometry, code="", name="f", fid="1"):
    return {
        "properties": {"id": fid, "kind": kind, "code": code, "name": name},
        "geometry": geometry,
    }


AREA = [square(0, 0, 10, 10)]


# ── los tres pasos de `geometry_intersects_rings`, uno por uno ─────────────────


def test_boxes_that_do_not_touch_are_discarded_first():
    assert not geometry_intersects_rings(polygon(square(20, 20, 21, 21)), AREA)


def test_a_zone_vertex_inside_the_area_intersects():
    assert geometry_intersects_rings(polygon(square(8, 8, 12, 12)), AREA)


def test_an_area_wholly_inside_the_zone_intersects_by_the_other_direction():
    """Ningún vértice de la zona cae en el área, pero el área cabe entera en la zona: 2.º sentido."""
    assert geometry_intersects_rings(polygon(square(-5, -5, 15, 15)), AREA)


def test_two_outlines_that_cross_without_any_vertex_inside_intersect_by_their_edges():
    """Un «+»: dos rectángulos largos y finos se cruzan y ningún vértice de uno cae en el otro."""
    area = [square(4, -10, 6, 20)]  # vertical
    zone = polygon(square(-10, 4, 20, 6))  # horizontal
    assert geometry_intersects_rings(zone, area)


def test_a_zone_in_a_hole_of_the_area_does_not_intersect():
    area = [
        square(0, 0, 10, 10),
        square(3, 3, 7, 7),
    ]  # anillo exterior y hueco (par-impar)
    assert not geometry_intersects_rings(polygon(square(4, 4, 6, 6)), area)
    assert geometry_intersects_rings(
        polygon(square(1, 1, 2, 2)), area
    )  # en el cuerpo, sí


def test_a_line_and_a_point_zone_are_handled():
    line = {"type": "LineString", "coordinates": [[-5, 5], [15, 5]]}
    assert geometry_intersects_rings(
        line, AREA
    )  # cruza de lado a lado, sin vértice dentro
    assert not geometry_intersects_rings(
        {"type": "Point", "coordinates": [20, 20]}, AREA
    )
    assert geometry_intersects_rings({"type": "Point", "coordinates": [5, 5]}, AREA)


def test_a_geometry_collection_counts_by_its_parts():
    collection = {
        "type": "GeometryCollection",
        "geometries": [
            {"type": "Point", "coordinates": [50, 50]},
            polygon(square(8, 8, 12, 12)),
        ],
    }
    assert geometry_intersects_rings(collection, AREA)


def test_an_empty_geometry_or_area_intersects_nothing():
    assert not geometry_intersects_rings({"type": "Polygon", "coordinates": []}, AREA)
    assert not geometry_intersects_rings(polygon(square(1, 1, 2, 2)), [])


# ── `features_in_area`: contenida / toca, y la unión de comunas ─────────────────


def test_contained_touches_and_outside_are_told_apart():
    found = features_in_area(
        [
            feature("restricted", polygon(square(2, 2, 4, 4)), "SC-R1", fid="in"),
            feature("danger", polygon(square(8, 8, 12, 12)), "SC-D1", fid="edge"),
            feature("prohibited", polygon(square(20, 20, 22, 22)), "SC-P1", fid="out"),
            feature("naval", polygon(square(-5, -5, 15, 15)), "N1", fid="big"),
        ],
        [AREA],
    )
    relations = {
        item["feature"]["properties"]["id"]: item["relation"] for item in found
    }
    assert relations == {"in": "contained", "edge": "touches", "big": "touches"}


def test_an_aerodrome_counts_only_when_it_is_inside_and_an_airstrip_never():
    found = features_in_area(
        [
            feature(
                "aerodrome", {"type": "Point", "coordinates": [5, 5]}, "SCIN", fid="in"
            ),
            feature(
                "airport", {"type": "Point", "coordinates": [50, 5]}, "SCOUT", fid="out"
            ),
            feature(
                "airstrip", {"type": "Point", "coordinates": [5, 6]}, "", fid="strip"
            ),
        ],
        [AREA],
    )
    assert [(i["feature"]["properties"]["id"], i["relation"]) for i in found] == [
        ("in", "contained")
    ]


def test_a_zone_across_two_neighbouring_communes_is_contained_in_their_region():
    """Dos comunas vecinas que se solapan un poco: la unión (por partes) contiene la zona; un par-impar
    sobre todos los anillos juntos habría contado el solapamiento como «fuera»."""
    west, east = [square(0, 0, 6, 10)], [square(5, 0, 10, 10)]
    across = feature("restricted", polygon(square(4, 4, 8, 6)), "SC-R2", fid="across")
    in_region = features_in_area([across], [west, east])
    assert [i["relation"] for i in in_region] == ["contained"]
    in_west = features_in_area([across], [west])
    assert [i["relation"] for i in in_west] == ["touches"]
    # La zona de la franja solapada (x 5-6) está en las dos comunas: en ninguna aparece como «fuera».
    sliver = feature("danger", polygon(square(5.2, 4, 5.8, 6)), "SC-D2", fid="s")
    assert features_in_area([sliver], [west])[0]["relation"] == "contained"
    assert features_in_area([sliver], [east])[0]["relation"] == "contained"
    assert features_in_area([sliver], [west, east])[0]["relation"] == "contained"


def test_a_zone_wholly_in_the_hole_of_the_area_is_left_out():
    area = [square(0, 0, 10, 10), square(3, 3, 7, 7)]
    found = features_in_area(
        [feature("restricted", polygon(square(4, 4, 6, 6)), "SC-R3")], [area]
    )
    assert found == []


def test_an_island_polygon_ring_is_read_with_even_odd_like_the_locator():
    islands = [square(0, 0, 2, 2), square(5, 5, 7, 7)]  # dos islas de la misma comuna
    inside = feature("restricted", polygon(square(5.5, 5.5, 6.5, 6.5)), "SC-R4")
    between = feature("restricted", polygon(square(3, 3, 4, 4)), "SC-R5")
    assert len(features_in_area([inside, between], [islands])) == 1


def test_features_without_geometry_are_skipped():
    assert features_in_area([feature("restricted", {}, "SC-R6")], [AREA]) == []
