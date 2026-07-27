"""GEO-2: hardened KML/KMZ parser and canonical document.

Corpus of well-formed inputs plus the malicious fixtures that must be rejected.
The generator and round-trip test land in GEO-3.
"""

import io
import zipfile

import pytest

from apps.geo.kml import canonical, parse_upload
from apps.geo.kml.errors import KmlImportError
from apps.geo.kml.parse import assert_wellformed_fragment, parse_kml_bytes

HAPPY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>CC716 Planificacion</name>
    <description>Plan de vuelo</description>
    <Style id="area">
      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
      <PolyStyle><color>7f0000ff</color><fill>1</fill></PolyStyle>
    </Style>
    <Folder>
      <name>Area de vuelo</name>
      <Placemark>
        <name>Poligono</name>
        <styleUrl>#area</styleUrl>
        <Polygon>
          <outerBoundaryIs><LinearRing><coordinates>
            -70.1,-23.1,0 -70.0,-23.1,0 -70.0,-23.0,0 -70.1,-23.0,0 -70.1,-23.1,0
          </coordinates></LinearRing></outerBoundaryIs>
          <innerBoundaryIs><LinearRing><coordinates>
            -70.06,-23.06 -70.04,-23.06 -70.04,-23.04 -70.06,-23.04 -70.06,-23.06
          </coordinates></LinearRing></innerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
    <Placemark>
      <name>Despegue</name>
      <Point><coordinates>-70.05,-23.05,120</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Ruta</name>
      <LineString><coordinates>-70.05,-23.05 -70.04,-23.04</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Torres</name>
      <MultiGeometry>
        <Point><coordinates>-70.05,-23.05</coordinates></Point>
        <Point><coordinates>-70.06,-23.06</coordinates></Point>
      </MultiGeometry>
    </Placemark>
    <Placemark>
      <name>Con datos</name>
      <ExtendedData>
        <Data name="altura_max"><value>120</value></Data>
      </ExtendedData>
      <Point><coordinates>-70.05,-23.05</coordinates></Point>
      <gx:balloonVisibility>1</gx:balloonVisibility>
    </Placemark>
    <NetworkLink><name>externo</name></NetworkLink>
  </Document>
</kml>
"""


def _make_kmz(kml_text=HAPPY_KML, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml_text)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


class TestHappyParsing:
    def test_document_metadata_and_shared_style(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        assert doc["name"] == "CC716 Planificacion"
        assert doc["description"] == "Plan de vuelo"
        assert "#area" in doc["shared_styles"]
        assert "LineStyle" in doc["shared_styles"]["#area"]["raw_xml"]

    def test_folder_and_feature_tree(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        kinds = [c["kind"] for c in doc["children"]]
        # folder, three placemarks, one placemark with data, and the raw NetworkLink
        assert kinds == ["folder", "placemark", "placemark", "placemark", "placemark", "raw"]
        folder = doc["children"][0]
        assert folder["name"] == "Area de vuelo"
        assert len(folder["children"]) == 1
        assert folder["children"][0]["geometry"]["type"] == "Polygon"

    def test_geometry_types_and_coordinates(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        by_name = {p["name"]: p for p in canonical.iter_placemarks(doc)}
        assert by_name["Despegue"]["geometry"] == {
            "type": "Point",
            "coordinates": [-70.05, -23.05, 120.0],
        }
        assert by_name["Ruta"]["geometry"]["type"] == "LineString"
        assert by_name["Torres"]["geometry"]["type"] == "GeometryCollection"
        assert len(by_name["Torres"]["geometry"]["geometries"]) == 2
        polygon = by_name["Poligono"]["geometry"]
        assert len(polygon["coordinates"]) == 2  # outer + inner ring
        assert polygon["coordinates"][0][0] == [-70.1, -23.1, 0.0]

    def test_extended_data_and_preserved_extras(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        con_datos = {p["name"]: p for p in canonical.iter_placemarks(doc)}["Con datos"]
        assert con_datos["extended_data"]["pairs"] == [["altura_max", "120"]]
        # The gx:* element has no structured home; it survives verbatim.
        assert any("balloonVisibility" in raw for raw in con_datos["extras"])

    def test_unsupported_container_child_preserved_as_raw(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        raw_nodes = [c for c in doc["children"] if c["kind"] == "raw"]
        assert len(raw_nodes) == 1
        assert "NetworkLink" in raw_nodes[0]["raw_xml"]

    def test_feature_count_and_bbox(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        assert canonical.count_features(doc) == 5
        west, south, east, north = canonical.compute_bbox(doc)
        assert west == pytest.approx(-70.1) and east == pytest.approx(-70.0)
        assert south == pytest.approx(-23.1) and north == pytest.approx(-23.0)

    def test_kmz_records_resource_names_without_storing_them(self):
        kmz = _make_kmz(extra={"files/icon.png": b"\x89PNG\r\n\x1a\n"})
        doc = parse_upload(kmz, "CC716_PLAN.kmz")
        assert doc["kmz_resources"] == ["files/icon.png"]
        assert canonical.count_features(doc) == 5

    def test_kml_upload_dispatch(self):
        doc = parse_upload(HAPPY_KML.encode("utf-8"), "plan.kml")
        assert doc["name"] == "CC716 Planificacion"


class TestMaliciousInputs:
    def test_doctype_is_rejected(self):
        payload = (
            b'<?xml version="1.0"?>\n'
            b'<!DOCTYPE kml [ <!ENTITY lol "lol"> ]>\n'
            b"<kml><Document></Document></kml>"
        )
        with pytest.raises(KmlImportError):
            parse_upload(payload, "x.kml")

    def test_not_xml_is_rejected(self):
        with pytest.raises(KmlImportError):
            parse_upload(b"this is not xml", "x.kml")

    def test_kmz_that_is_not_a_zip_is_rejected(self):
        with pytest.raises(KmlImportError):
            parse_upload(b"not a zip archive", "x.kmz")

    def test_kmz_with_traversal_entry_is_rejected(self):
        with pytest.raises(KmlImportError):
            parse_upload(_make_kmz(extra={"../evil.txt": b"x"}), "x.kmz")

    def test_kmz_with_too_many_entries_is_rejected(self):
        extra = {f"files/f{i}.bin": b"x" for i in range(210)}
        with pytest.raises(KmlImportError):
            parse_upload(_make_kmz(extra=extra), "x.kmz")

    def test_kmz_compression_bomb_ratio_is_rejected(self):
        # 2 MB of zeros deflates to a few KB -> ratio far over the 100:1 guard.
        bomb = _make_kmz(extra={"big.bin": b"\x00" * (2 * 1024 * 1024)})
        with pytest.raises(KmlImportError):
            parse_upload(bomb, "x.kmz")

    def test_out_of_range_coordinate_is_rejected(self):
        payload = (
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            "<Placemark><name>bad</name>"
            "<Point><coordinates>999,10</coordinates></Point>"
            "</Placemark></Document></kml>"
        ).encode("utf-8")
        with pytest.raises(KmlImportError):
            parse_upload(payload, "x.kml")

    def test_unknown_extension_is_rejected(self):
        with pytest.raises(KmlImportError):
            parse_upload(HAPPY_KML.encode("utf-8"), "plan.txt")


class TestCanonicalGuards:
    def test_feature_cap_enforced(self):
        doc = canonical.empty_document()
        doc["children"] = [
            {
                "kind": "placemark",
                "uid": f"p-{i}",
                "name": "x",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "extras": [],
            }
            for i in range(canonical.MAX_FEATURES + 1)
        ]
        with pytest.raises(KmlImportError):
            canonical.validate_document(doc, reparse_raw=False)

    def test_checksum_is_stable_and_order_independent(self):
        doc = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
        assert canonical.canonical_checksum(doc) == canonical.canonical_checksum(doc)

    def test_malformed_stored_fragment_is_flagged(self):
        with pytest.raises(KmlImportError):
            assert_wellformed_fragment("<a></b>")
