"""Generate a KML document from a canonical "AeroKML JSON" tree.

The inverse of parse.py. Structured nodes are rebuilt as KML elements; preserved
raw fragments (styles, extras, raw children, ExtendedData) are re-parsed with
the hardened parser and re-emitted in place, so anything the editor did not
touch comes back byte-equivalent. KMZ packaging (copying the original's embedded
resources) is GEO-10; this module produces the KML bytes.
"""

from lxml import etree

from .parse import _hardened_parser

KML_NS = "http://www.opengis.net/kml/2.2"


def _q(tag):
    return f"{{{KML_NS}}}{tag}"


def _text_child(parent, tag, value):
    if value:
        etree.SubElement(parent, _q(tag)).text = value


def _append_raw(parent, raw_xml):
    parent.append(etree.fromstring(raw_xml.encode("utf-8"), _hardened_parser()))


def _coord_text(points):
    return " ".join(",".join(_format_number(n) for n in point) for point in points)


def _format_number(number):
    # Integers keep no trailing ".0" so exported coordinates read like the input.
    if isinstance(number, float) and number.is_integer():
        return str(int(number))
    return repr(number)


def build_kml_bytes(document):
    """Return KML bytes for a canonical document."""
    root = etree.Element(_q("kml"), nsmap={None: KML_NS})
    doc_el = etree.SubElement(root, _q("Document"))

    _text_child(doc_el, "name", document.get("name", ""))
    _text_child(doc_el, "description", document.get("description", ""))
    for style in document.get("shared_styles", {}).values():
        _append_raw(doc_el, style["raw_xml"])
    for extra in document.get("doc_extras", []):
        _append_raw(doc_el, extra)
    for node in document.get("children", []):
        _build_node(doc_el, node)

    # No pretty_print: it rewrites whitespace inside the raw fragments we
    # re-insert verbatim, which would break the round-trip guarantee that
    # untouched content comes back byte-equivalent. Google Earth reads compact
    # KML fine.
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _build_node(parent, node):
    kind = node.get("kind")
    if kind == "folder":
        _build_folder(parent, node)
    elif kind == "placemark":
        _build_placemark(parent, node)
    elif kind == "raw":
        _append_raw(parent, node["raw_xml"])


def _build_folder(parent, node):
    folder = etree.SubElement(parent, _q("Folder"))
    _text_child(folder, "name", node.get("name", ""))
    _text_child(folder, "description", node.get("description", ""))
    if node.get("visibility") is False:
        etree.SubElement(folder, _q("visibility")).text = "0"
    for child in node.get("children", []):
        _build_node(folder, child)


def _build_placemark(parent, node):
    placemark = etree.SubElement(parent, _q("Placemark"))
    _text_child(placemark, "name", node.get("name", ""))
    _text_child(placemark, "description", node.get("description", ""))
    if node.get("visibility") is False:
        etree.SubElement(placemark, _q("visibility")).text = "0"
    if node.get("style_url"):
        etree.SubElement(placemark, _q("styleUrl")).text = node["style_url"]
    color = node.get("color")
    if color:
        placemark.append(_style_element(color))
    extended = node.get("extended_data")
    if extended and extended.get("raw_xml"):
        _append_raw(placemark, extended["raw_xml"])
    if node.get("geometry"):
        _build_geometry(placemark, node["geometry"])
    for extra in node.get("extras", []):
        # LV-282: con un color elegido, el `<Style>` en línea que trajo el archivo
        # original sobra: KML admite un solo StyleSelector por Placemark y el que
        # el usuario eligió es el que manda. Los demás extras se conservan.
        if color and _is_style_fragment(extra):
            continue
        _append_raw(placemark, extra)


def _is_style_fragment(raw_xml):
    element = etree.fromstring(raw_xml.encode("utf-8"), _hardened_parser())
    return etree.QName(element).localname == "Style"


def _kml_color(rgb, alpha):
    """`#rrggbb` -> `aabbggrr`, el orden de bytes de KML (no el de CSS)."""
    r, g, b = rgb[1:3], rgb[3:5], rgb[5:7]
    return f"{alpha}{b}{g}{r}".lower()


def _style_element(color):
    """El `<Style>` en línea de un placemark con color de capa.

    Línea y punto opacos, relleno translúcido: es lo que el editor dibuja
    (`weight: 3, fillOpacity: 0.15` en `main.js`), así que Google Earth muestra
    el mismo color que el mapa.
    """
    style = etree.Element(_q("Style"))
    line = etree.SubElement(style, _q("LineStyle"))
    etree.SubElement(line, _q("color")).text = _kml_color(color, "ff")
    etree.SubElement(line, _q("width")).text = "3"
    poly = etree.SubElement(style, _q("PolyStyle"))
    etree.SubElement(poly, _q("color")).text = _kml_color(color, "26")
    icon = etree.SubElement(style, _q("IconStyle"))
    etree.SubElement(icon, _q("color")).text = _kml_color(color, "ff")
    return style


def _build_geometry(parent, geometry):
    gtype = geometry.get("type")
    if gtype == "Point":
        point = etree.SubElement(parent, _q("Point"))
        coords = geometry.get("coordinates")
        etree.SubElement(point, _q("coordinates")).text = _coord_text(
            [coords] if coords else []
        )
    elif gtype == "LineString":
        line = etree.SubElement(parent, _q("LineString"))
        etree.SubElement(line, _q("coordinates")).text = _coord_text(
            geometry.get("coordinates", [])
        )
    elif gtype == "Polygon":
        polygon = etree.SubElement(parent, _q("Polygon"))
        for index, ring in enumerate(geometry.get("coordinates", [])):
            boundary_tag = "outerBoundaryIs" if index == 0 else "innerBoundaryIs"
            boundary = etree.SubElement(polygon, _q(boundary_tag))
            linear_ring = etree.SubElement(boundary, _q("LinearRing"))
            etree.SubElement(linear_ring, _q("coordinates")).text = _coord_text(ring)
    elif gtype == "GeometryCollection":
        multi = etree.SubElement(parent, _q("MultiGeometry"))
        for sub in geometry.get("geometries", []):
            _build_geometry(multi, sub)
