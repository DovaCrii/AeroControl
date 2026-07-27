"""Hardened KML parsing: bytes -> canonical "AeroKML JSON".

Every parse goes through a locked-down lxml parser (no entities, no DTD, no
network) with a DOCTYPE pre-check, so XXE and billion-laughs die before libxml2
sees the document. Supported elements become structured canonical nodes; every
other element is preserved verbatim as raw XML in its position, so an edit never
silently drops the parts of a plan we do not model.
"""

from lxml import etree

from . import canonical
from .errors import KmlImportError

# Elements handled structurally in a feature container; everything else in a
# container is preserved as a raw child node, in order.
_MAX_NODES = 200_000
_MAX_DEPTH = 32


def _hardened_parser():
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        dtd_validation=False,
        no_network=True,
        huge_tree=False,
    )


def _reject_doctype(data):
    head = data[:4096].lstrip()
    if b"<!doctype" in head.lower():
        raise KmlImportError("The document declares a DOCTYPE, which is not allowed.")


def _localname(element):
    if not isinstance(element.tag, str):  # comment / processing instruction
        return None
    return etree.QName(element).localname


def _raw(element):
    return etree.tostring(element, encoding="unicode")


def assert_wellformed_fragment(xml_string):
    """Re-parse a stored raw fragment with the hardened parser.

    Called from canonical.validate_document so raw XML from the database (or a
    commit payload) is never trusted more than a fresh upload.
    """
    data = xml_string.encode("utf-8")
    # Same DOCTYPE guard as a fresh upload: a commit payload is the first place
    # client-supplied raw_xml re-enters, so it gets the byte pre-check too.
    _reject_doctype(data)
    try:
        etree.fromstring(data, _hardened_parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise KmlImportError("A stored XML fragment is not well-formed.") from exc


def parse_kml_bytes(data):
    """Parse KML bytes into a canonical document. Raises KmlImportError."""
    _reject_doctype(data)
    try:
        root = etree.fromstring(data, _hardened_parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise KmlImportError("The file is not valid XML/KML.") from exc

    node_count = sum(1 for _ in root.iter())
    if node_count > _MAX_NODES:
        raise KmlImportError("The KML has more elements than the limit allows.")

    document = canonical.empty_document()
    container = _root_container(root)
    _fill_container(container, document, target=document, depth=0)
    return document


def _root_container(root):
    """Return the element whose children are the plan's features.

    Usually <kml><Document>...; also tolerates <kml><Folder> or features placed
    directly under <kml>.
    """
    if _localname(root) != "kml":
        return root
    for child in root:
        if _localname(child) == "Document":
            return child
    return root  # features / folders sit directly under <kml>


def _fill_container(element, document, *, target, depth):
    """Populate `target` (document or folder node) from a container element.

    Sets name/description/visibility, bubbles id'd styles into the document, and
    appends child nodes (folders, placemarks, raw) in source order.
    """
    if depth > _MAX_DEPTH:
        raise KmlImportError("The folder structure is nested too deep.")

    children = []
    for child in element:
        name = _localname(child)
        if name is None:
            continue
        if name == "name":
            target["name"] = child.text or ""
        elif name == "description":
            target["description"] = child.text or ""
        elif name == "visibility" and "visibility" in target:
            target["visibility"] = (child.text or "").strip() not in ("0", "false")
        elif name in ("Style", "StyleMap") and child.get("id"):
            style_id = "#" + child.get("id")
            document["shared_styles"][style_id] = {
                "raw_xml": _raw(child),
                "resolved": _resolve_style(child),
            }
        elif name == "Folder":
            children.append(_parse_folder(child, document, depth + 1))
        elif name == "Placemark":
            children.append(_parse_placemark(child))
        else:
            children.append(
                {"kind": "raw", "uid": canonical.new_uid("raw"), "raw_xml": _raw(child)}
            )
    target["children"] = children


def _parse_folder(element, document, depth):
    node = {
        "kind": "folder",
        "uid": canonical.new_uid("folder"),
        "name": "",
        "description": "",
        "visibility": True,
        "children": [],
    }
    _fill_container(element, document, target=node, depth=depth)
    return node


_GEOMETRY_TAGS = {"Point", "LineString", "Polygon", "MultiGeometry"}


def _parse_placemark(element):
    node = {
        "kind": "placemark",
        "uid": canonical.new_uid("placemark"),
        "name": "",
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": None,
        "extended_data": None,
        "extras": [],
    }
    for child in element:
        name = _localname(child)
        if name is None:
            continue
        if name == "name":
            node["name"] = child.text or ""
        elif name == "description":
            node["description"] = child.text or ""
        elif name == "visibility":
            node["visibility"] = (child.text or "").strip() not in ("0", "false")
        elif name == "styleUrl":
            node["style_url"] = (child.text or "").strip() or None
        elif name == "ExtendedData":
            node["extended_data"] = {
                "raw_xml": _raw(child),
                "pairs": _resolve_extended_data(child),
            }
        elif name in _GEOMETRY_TAGS:
            node["geometry"] = _parse_geometry(child)
        else:
            # Inline styles, LookAt, TimeStamp, gx:* ... preserved verbatim.
            node["extras"].append(_raw(child))
    return node


def _parse_geometry(element):
    name = _localname(element)
    if name == "Point":
        coords = _coords(element)
        return {"type": "Point", "coordinates": coords[0] if coords else []}
    if name == "LineString":
        return {"type": "LineString", "coordinates": _coords(element)}
    if name == "Polygon":
        return {"type": "Polygon", "coordinates": _polygon_rings(element)}
    if name == "MultiGeometry":
        geometries = [
            _parse_geometry(child)
            for child in element
            if _localname(child) in _GEOMETRY_TAGS
        ]
        return {"type": "GeometryCollection", "geometries": geometries}
    raise KmlImportError(f"Unsupported geometry element: {name!r}.")


def _polygon_rings(polygon):
    rings = []
    for boundary_name in ("outerBoundaryIs", "innerBoundaryIs"):
        for boundary in polygon:
            if _localname(boundary) != boundary_name:
                continue
            for ring in boundary:
                if _localname(ring) == "LinearRing":
                    rings.append(_coords(ring))
    return rings


def _coords(element):
    """Parse the <coordinates> descendant into a list of [lon, lat, alt?]."""
    for child in element.iter():
        if _localname(child) == "coordinates":
            return _parse_coord_text(child.text or "")
    return []


def _parse_coord_text(text):
    points = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            raise KmlImportError("Malformed coordinate tuple in the KML.")
        try:
            point = [float(parts[0]), float(parts[1])]
            if len(parts) >= 3 and parts[2] != "":
                point.append(float(parts[2]))
        except ValueError as exc:
            raise KmlImportError("Non-numeric coordinate in the KML.") from exc
        points.append(point)
    return points


def _resolve_style(element):
    """Best-effort style summary for the inspector; export uses the raw XML."""
    resolved = {}
    for descendant in element.iter():
        name = _localname(descendant)
        if name == "color" and (descendant.text or "").strip():
            resolved.setdefault("color", descendant.text.strip())
        elif name == "width" and (descendant.text or "").strip():
            resolved["width"] = descendant.text.strip()
        elif name == "href" and (descendant.text or "").strip():
            resolved["icon"] = descendant.text.strip()
    return resolved


def _resolve_extended_data(element):
    """Editable view of <Data name=..><value>..</value></Data> pairs."""
    pairs = []
    for data in element:
        if _localname(data) != "Data":
            continue
        key = data.get("name") or ""
        value = ""
        for child in data:
            if _localname(child) == "value":
                value = child.text or ""
        pairs.append([key, value])
    return pairs
