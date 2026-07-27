"""The canonical "AeroKML JSON" document: shape, helpers and validation.

Master format for a plan version (NOT GeoJSON). A faithful tree of the KML with
sibling order preserved; unsupported elements survive as raw XML in place. See
docs/dev/geo-editor-plan.md section 2.

Shared by the parser (import), the generator (export, GEO-3) and the commit API
(GEO-6), so the same caps and validation apply wherever a document enters.
"""

import hashlib
import json
import uuid

from .errors import KmlImportError

SCHEMA_VERSION = 1

# Hard caps, enforced on import and on every commit.
MAX_CONTENT_BYTES = 8 * 1024 * 1024
MAX_FEATURES = 2000

GEOMETRY_TYPES = {"Point", "LineString", "Polygon", "GeometryCollection"}


def new_uid(kind):
    """Stable per-node id. The prefix keeps diffs between versions readable."""
    return f"{kind[:1]}-{uuid.uuid4().hex[:12]}"


def empty_document():
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "",
        "description": "",
        "shared_styles": {},
        "kmz_resources": [],
        "doc_extras": [],
        "children": [],
    }


def iter_placemarks(document):
    """Yield every placemark node, depth-first, in document order."""

    def walk(nodes):
        for node in nodes:
            if node.get("kind") == "placemark":
                yield node
            elif node.get("kind") == "folder":
                yield from walk(node.get("children", []))

    yield from walk(document.get("children", []))


def count_features(document):
    return sum(1 for _ in iter_placemarks(document))


def _iter_coords(geometry):
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        if coords:
            yield coords
    elif gtype == "LineString":
        yield from coords or []
    elif gtype == "Polygon":
        for ring in coords or []:
            yield from ring
    elif gtype == "GeometryCollection":
        for sub in geometry.get("geometries", []):
            yield from _iter_coords(sub)


def compute_bbox(document):
    """(west, south, east, north) over all geometries, or None if empty."""
    west = south = east = north = None
    for placemark in iter_placemarks(document):
        geometry = placemark.get("geometry")
        if not geometry:
            continue
        for point in _iter_coords(geometry):
            lon, lat = point[0], point[1]
            west = lon if west is None else min(west, lon)
            east = lon if east is None else max(east, lon)
            south = lat if south is None else min(south, lat)
            north = lat if north is None else max(north, lat)
    if west is None:
        return None
    return (west, south, east, north)


def canonical_json(document):
    """Deterministic serialization: stable across machines for checksums."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def canonical_checksum(document):
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def size_bytes(document):
    return len(canonical_json(document).encode("utf-8"))


def _validate_coord(point, where):
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        raise KmlImportError(f"Malformed coordinate in {where}.")
    lon, lat = point[0], point[1]
    if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        raise KmlImportError(
            f"Coordinate out of range in {where}: lon={lon}, lat={lat}."
        )


def validate_document(document, *, reparse_raw=True):
    """Validate a canonical document. Raises KmlImportError on any problem.

    Used both on import (parser output) and on commit (client-supplied JSON),
    so every raw_xml fragment is re-parsed with the hardened parser -- the
    database is not trusted any more than an upload is.
    """
    if not isinstance(document, dict):
        raise KmlImportError("The document must be an object.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise KmlImportError("Unsupported document schema version.")

    if size_bytes(document) > MAX_CONTENT_BYTES:
        raise KmlImportError("The plan exceeds the 8 MB content limit.")

    features = count_features(document)
    if features > MAX_FEATURES:
        raise KmlImportError(
            f"The plan has {features} features; the limit is {MAX_FEATURES}."
        )

    for placemark in iter_placemarks(document):
        geometry = placemark.get("geometry")
        if geometry is None:
            continue
        if geometry.get("type") not in GEOMETRY_TYPES:
            raise KmlImportError(f"Unsupported geometry: {geometry.get('type')!r}.")
        for point in _iter_coords(geometry):
            _validate_coord(point, placemark.get("name") or "a placemark")

    if reparse_raw:
        # Imported lazily to avoid a circular import (parser imports canonical).
        from .parse import assert_wellformed_fragment

        for fragment in _iter_raw_fragments(document):
            assert_wellformed_fragment(fragment)


def _iter_raw_fragments(document):
    for value in document.get("shared_styles", {}).values():
        raw = value.get("raw_xml")
        if raw:
            yield raw
    yield from document.get("doc_extras", [])

    def walk(nodes):
        for node in nodes:
            for raw in node.get("extras", []) or []:
                yield raw
            if node.get("kind") == "raw" and node.get("raw_xml"):
                yield node["raw_xml"]
            extended = node.get("extended_data")
            if extended and extended.get("raw_xml"):
                yield extended["raw_xml"]
            if node.get("kind") == "folder":
                yield from walk(node.get("children", []))

    yield from walk(document.get("children", []))
