"""Geometría pura del espacio aéreo (LV-357, fase 2)."""

import math

import pytest

from apps.geo import airspace_geometry as g

# Caja de ~9,3 km x ~11 km sobre Santiago, con un hueco al centro.
OUTER = [
    [-70.70, -33.50],
    [-70.60, -33.50],
    [-70.60, -33.40],
    [-70.70, -33.40],
    [-70.70, -33.50],
]
HOLE = [
    [-70.66, -33.46],
    [-70.64, -33.46],
    [-70.64, -33.44],
    [-70.66, -33.44],
    [-70.66, -33.46],
]
BOX = {"type": "Polygon", "coordinates": [OUTER]}
DONUT = {"type": "Polygon", "coordinates": [OUTER, HOLE]}
LINE = {"type": "LineString", "coordinates": [[-70.80, -33.45], [-70.75, -33.45]]}


def feature(kind, geometry, code="", name=""):
    return {
        "type": "Feature",
        "properties": {"kind": kind, "code": code, "name": name},
        "geometry": geometry,
    }


def point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


class TestPointInPolygon:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (-33.45, -70.65, True),  # dentro
            (-33.30, -70.65, False),  # al norte
            (-33.45, -70.50, False),  # al este
            (-33.50, -70.65, True),  # sobre el borde sur
            (-33.45, -70.60, True),  # sobre el borde este
            (-33.40, -70.70, True),  # vértice
        ],
    )
    def test_box(self, lat, lon, expected):
        assert g.point_in_polygon(lat, lon, BOX["coordinates"]) is expected

    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (-33.45, -70.65, False),  # en el hueco
            (-33.47, -70.65, True),  # fuera del hueco, dentro de la caja
            (-33.45, -70.66, True),  # sobre el borde del hueco
        ],
    )
    def test_hole(self, lat, lon, expected):
        assert g.point_in_polygon(lat, lon, DONUT["coordinates"]) is expected

    def test_degenerate_polygon_contains_nothing(self):
        assert g.point_in_polygon(0, 0, []) is False
        assert g.point_in_polygon(0, 0, [[[0, 0], [1, 1]]]) is False

    def test_multipolygon(self):
        far = [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 10.0]]]
        geometry = {"type": "MultiPolygon", "coordinates": [BOX["coordinates"], far]}
        assert g.point_in_geometry(-33.45, -70.65, geometry)
        assert g.point_in_geometry(10.3, 10.7, geometry)
        assert not g.point_in_geometry(0, 0, geometry)


class TestDistances:
    def test_to_edge_from_outside_matches_haversine_scale(self):
        # 0,01 grados de latitud al norte del borde norte: ~1,11 km.
        d = g.distance_to_polygon_edge_km(-33.39, -70.65, BOX["coordinates"])
        assert d == pytest.approx(1.113, abs=0.01)

    def test_to_edge_from_inside_is_not_zero(self):
        d = g.distance_to_polygon_edge_km(-33.41, -70.65, BOX["coordinates"])
        assert d == pytest.approx(1.113, abs=0.01)

    def test_hole_edge_counts(self):
        # Centro del hueco: el borde más cercano es el del hueco, no el exterior.
        d = g.distance_to_polygon_edge_km(-33.45, -70.65, DONUT["coordinates"])
        assert d == pytest.approx(0.929, abs=0.02)

    def test_geometry_distance_is_zero_inside(self):
        assert g.distance_to_geometry_km(-33.45, -70.65, BOX) == 0.0

    def test_geometry_distance_in_hole_is_to_hole_edge(self):
        d = g.distance_to_geometry_km(-33.45, -70.65, DONUT)
        assert d == pytest.approx(0.929, abs=0.02)

    def test_to_line(self):
        d = g.distance_to_line_km(-33.44, -70.775, LINE["coordinates"])
        assert d == pytest.approx(1.113, abs=0.01)
        assert g.distance_to_geometry_km(-33.44, -70.775, LINE) == pytest.approx(d)

    def test_to_line_beyond_the_end_uses_the_endpoint(self):
        d = g.distance_to_line_km(-33.45, -70.70, LINE["coordinates"])
        assert d == pytest.approx(
            g.distance_km(-33.45, -70.70, -33.45, -70.75), abs=0.02
        )

    def test_to_point(self):
        d = g.distance_to_geometry_km(-33.45, -70.65, point(-70.65, -33.46))
        assert d == pytest.approx(1.113, abs=0.01)

    def test_empty_geometry_is_infinite(self):
        assert math.isinf(
            g.distance_to_geometry_km(0, 0, {"type": "Point", "coordinates": []})
        )

    def test_km_nm_roundtrip(self):
        assert g.km_to_nm(1.852) == pytest.approx(1.0)
        assert g.nm_to_km(g.km_to_nm(12.5)) == pytest.approx(12.5)
        assert g.distance_nm(0, 0, 0, 1) == pytest.approx(
            g.distance_km(0, 0, 0, 1) / 1.852
        )


class TestBearing:
    @pytest.mark.parametrize(
        ("target", "expected"),
        [((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), 270)],
    )
    def test_cardinals(self, target, expected):
        assert g.bearing_deg(0, 0, *target) == pytest.approx(expected, abs=0.01)

    def test_always_in_range(self):
        assert 0 <= g.bearing_deg(-33.4, -70.6, -33.5, -70.8) < 360


class TestCircles:
    def test_circle_crosses_edge_without_containing_center(self):
        # Centro ~1,85 km al este del borde este (-70.60); radio 3 km lo cruza.
        assert not g.point_in_geometry(-33.45, -70.58, BOX)
        assert g.circle_intersects_geometry(-33.45, -70.58, 3.0, BOX)
        assert not g.circle_intersects_geometry(-33.45, -70.58, 1.0, BOX)

    def test_circle_containing_the_whole_polygon(self):
        assert g.circle_intersects_geometry(-33.45, -70.65, 50.0, BOX)

    def test_circle_reaching_a_polygon_that_sits_entirely_inside_it(self):
        small = {
            "type": "Polygon",
            "coordinates": [[[0.01, 0.01], [0.02, 0.01], [0.02, 0.02], [0.01, 0.01]]],
        }
        assert g.circle_intersects_geometry(0.0, 0.0, 5.0, small)

    def test_center_inside_always_intersects(self):
        assert g.circle_intersects_geometry(-33.45, -70.65, 0.01, BOX)

    def test_center_in_hole_needs_to_reach_the_ring(self):
        assert not g.circle_intersects_geometry(-33.45, -70.65, 0.3, DONUT)
        assert g.circle_intersects_geometry(-33.45, -70.65, 1.5, DONUT)

    def test_circle_vs_line_and_point(self):
        assert g.circle_intersects_geometry(-33.44, -70.775, 1.5, LINE)
        assert not g.circle_intersects_geometry(-33.44, -70.775, 0.5, LINE)
        assert g.circle_intersects_geometry(-33.45, -70.65, 2.0, point(-70.65, -33.46))

    def test_circle_circle(self):
        # 0,1 grado de longitud en el ecuador ~ 11,1 km.
        assert g.circle_intersects_circle(0, 0, 6, 0, 0.1, 6)
        assert not g.circle_intersects_circle(0, 0, 5, 0, 0.1, 5)
        assert g.circle_intersects_circle(0, 0, 1, 0, 0, 1)  # concéntricos


class TestBbox:
    def test_bbox_of_each_type(self):
        assert g.bbox_of(BOX) == (-70.70, -33.50, -70.60, -33.40)
        assert g.bbox_of(LINE) == (-70.80, -33.45, -70.75, -33.45)
        assert g.bbox_of(point(1, 2)) == (1, 2, 1, 2)
        assert g.bbox_of({"type": "Polygon", "coordinates": []}) is None

    def test_prefilter_never_drops_what_is_within_margin(self):
        bbox = g.bbox_of(BOX)
        # 5 km al norte del borde norte.
        lat = -33.40 + 5 / 111.32
        assert g.bbox_near(bbox, lat, -70.65, 6.0)
        assert not g.bbox_near(bbox, lat, -70.65, 4.0)
        assert not g.bbox_near(None, 0, 0, 100)

    def test_prefilter_margin_widens_with_latitude(self):
        bbox = (-70.0, -80.0, -69.0, -79.0)
        # 5 km al este a 79 S son ~0,24 grados de longitud, no 0,045.
        east = -69.0 + 5 / (111.32 * math.cos(math.radians(79)))
        assert g.bbox_near(bbox, -79.5, east - 0.001, 5.0)


class TestNearby:
    FEATURES = [
        feature("restricted", BOX, "SC-R1"),
        feature("danger", DONUT, "SC-D2"),
        feature("prohibited", LINE, "SC-P3"),
        feature("prohibited", point(-70.50, -33.45), "SC-P4"),
        feature("aerodrome", point(-70.70, -33.40), "SCAA"),
        feature("airport", point(-70.00, -33.40), "SCBB"),
        feature("aerodrome", point(-60.00, -33.40), "SCCC"),
        feature("airstrip", point(-70.651, -33.451), "STRIP"),
    ]

    def codes(self, entries):
        return [e["feature"]["properties"]["code"] for e in entries]

    def test_containing_within_and_aerodromes(self):
        result = g.nearby(-33.45, -70.62, self.FEATURES, within_km=5, aerodromes=2)
        assert self.codes(result["containing"]) == ["SC-R1", "SC-D2"]
        assert result["within"] == []
        assert self.codes(result["aerodromes"]) == ["SCAA", "SCBB"]

    def test_a_point_in_a_hole_is_near_the_zone_not_inside_it(self):
        result = g.nearby(-33.45, -70.65, self.FEATURES, within_km=5)
        assert self.codes(result["containing"]) == ["SC-R1"]
        assert self.codes(result["within"]) == ["SC-D2"]
        assert result["within"][0]["distance_km"] == pytest.approx(0.929, abs=0.02)

    def test_within_sorted_by_distance(self):
        result = g.nearby(-33.45, -70.45, self.FEATURES, within_km=20)
        assert self.codes(result["containing"]) == []
        assert self.codes(result["within"]) == ["SC-P4", "SC-R1", "SC-D2"]
        distances = [e["distance_km"] for e in result["within"]]
        assert distances == sorted(distances)

    def test_within_excludes_what_is_farther(self):
        result = g.nearby(-33.45, -70.45, self.FEATURES, within_km=6)
        assert self.codes(result["within"]) == ["SC-P4"]

    def test_airstrips_are_neither_zones_nor_aerodromes_by_default(self):
        result = g.nearby(-33.451, -70.651, self.FEATURES, aerodromes=10)
        everything = (
            self.codes(result["containing"])
            + self.codes(result["within"])
            + self.codes(result["aerodromes"])
        )
        assert "STRIP" not in everything
        with_strips = g.nearby(
            -33.451,
            -70.651,
            self.FEATURES,
            aerodromes=10,
            aerodrome_kinds=("aerodrome", "airport", "airstrip"),
        )
        assert self.codes(with_strips["aerodromes"])[0] == "STRIP"

    def test_aerodrome_entry_has_km_nm_and_bearing(self):
        result = g.nearby(-33.40, -70.80, self.FEATURES, aerodromes=1)
        entry = result["aerodromes"][0]
        assert entry["feature"]["properties"]["code"] == "SCAA"
        assert entry["distance_nm"] == pytest.approx(entry["distance_km"] / 1.852)
        assert entry["bearing_deg"] == pytest.approx(90, abs=0.5)

    def test_zero_aerodromes_and_no_features(self):
        assert g.nearby(0, 0, [], aerodromes=3) == {
            "containing": [],
            "within": [],
            "aerodromes": [],
        }
        assert g.nearby(-33.45, -70.62, self.FEATURES, aerodromes=0)["aerodromes"] == []
