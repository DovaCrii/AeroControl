"""GEO-3: canonical -> KML generator and the round-trip guarantee.

The core promise of the module: importing, exporting and re-importing a plan
does not change it. Comparison is semantic — uids are dropped and every raw XML
fragment is C14N-normalized — so redundant namespace declarations or attribute
order from lxml re-serialization do not count as differences, but any real loss
of a folder, feature, geometry, style or preserved fragment does.
"""

import copy

from lxml import etree

from apps.geo.kml import canonical
from apps.geo.kml.build import build_kml_bytes
from apps.geo.kml.parse import parse_kml_bytes
from apps.geo.test_kml import HAPPY_KML


def _c14n(raw_xml):
    return etree.canonicalize(raw_xml)


def _normalize_node(node):
    node = dict(node)
    node.pop("uid", None)
    if "extras" in node:
        node["extras"] = [_c14n(x) for x in node["extras"]]
    extended = node.get("extended_data")
    if extended and extended.get("raw_xml"):
        node["extended_data"] = {
            "pairs": extended.get("pairs", []),
            "raw_xml": _c14n(extended["raw_xml"]),
        }
    if node.get("kind") == "raw":
        node["raw_xml"] = _c14n(node["raw_xml"])
    if node.get("kind") == "folder":
        node["children"] = [_normalize_node(c) for c in node.get("children", [])]
    return node


def _normalize(document):
    doc = copy.deepcopy(document)
    doc["shared_styles"] = {
        key: {
            "resolved": value.get("resolved", {}),
            "raw_xml": _c14n(value["raw_xml"]),
        }
        for key, value in doc.get("shared_styles", {}).items()
    }
    doc["doc_extras"] = [_c14n(x) for x in doc.get("doc_extras", [])]
    doc["children"] = [_normalize_node(n) for n in doc.get("children", [])]
    return doc


def test_round_trip_preserves_the_document():
    original = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
    reimported = parse_kml_bytes(build_kml_bytes(original))
    assert _normalize(reimported) == _normalize(original)


def test_round_trip_is_a_fixed_point():
    once = build_kml_bytes(parse_kml_bytes(HAPPY_KML.encode("utf-8")))
    twice = build_kml_bytes(parse_kml_bytes(once))
    assert _normalize(parse_kml_bytes(twice)) == _normalize(parse_kml_bytes(once))


def test_exported_kml_is_valid_and_keeps_features():
    original = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
    exported = build_kml_bytes(original)
    # Real XML with a kml root.
    assert exported.lstrip().startswith(b"<?xml")
    reimported = parse_kml_bytes(exported)
    names_before = [p["name"] for p in canonical.iter_placemarks(original)]
    names_after = [p["name"] for p in canonical.iter_placemarks(reimported)]
    assert names_before == names_after
    assert canonical.compute_bbox(original) == canonical.compute_bbox(reimported)


def test_unsupported_elements_survive_export():
    original = parse_kml_bytes(HAPPY_KML.encode("utf-8"))
    exported = build_kml_bytes(original).decode("utf-8")
    # The NetworkLink (a raw child) and the gx:* placemark extra must reappear.
    assert "NetworkLink" in exported
    assert "balloonVisibility" in exported
    # And the shared style survives with its id.
    assert 'id="area"' in exported
