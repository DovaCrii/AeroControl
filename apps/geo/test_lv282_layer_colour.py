"""LV-282: el color de capa elegido en el editor viaja al KML.

Pedido del usuario (2026-10-06): *"poder cambiar el color de lo que está
dibujando"*. El color vive en el placemark (`color`, `#rrggbb`), se valida al
guardar y `build.py` lo escribe como un `<Style>` en línea, en el orden de bytes
de KML (`aabbggrr`), que es el que se invierte con facilidad.
"""

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from lxml import etree

from apps.geo.kml import canonical
from apps.geo.kml.build import build_kml_bytes
from apps.geo.kml.errors import KmlImportError
from apps.geo.kml.parse import parse_kml_bytes
from apps.geo.test_kml import HAPPY_KML

NS = {"k": "http://www.opengis.net/kml/2.2"}


def _document():
    return parse_kml_bytes(HAPPY_KML.encode("utf-8"))


def _first_placemark(document):
    return next(canonical.iter_placemarks(document))


def _styles_of_first_placemark(document):
    root = etree.fromstring(build_kml_bytes(document))
    placemark = root.find(".//k:Placemark", NS)
    return placemark.findall("k:Style", NS)


class TestValidation:
    @pytest.mark.parametrize("value", ["#0f9f95", "#FFAA00", "#000000"])
    def test_a_hex_colour_is_accepted(self, value):
        document = _document()
        _first_placemark(document)["color"] = value

        canonical.validate_document(document)

    @pytest.mark.parametrize(
        "value",
        ["red", "#fff", "#12345", "#1234567", "0f9f95", "#gggggg", "", 7, ["#000000"]],
    )
    def test_anything_else_is_rejected(self, value):
        document = _document()
        _first_placemark(document)["color"] = value

        with pytest.raises(KmlImportError):
            canonical.validate_document(document)

    def test_a_document_without_colours_is_still_valid(self):
        canonical.validate_document(_document())


class TestExport:
    def test_the_colour_becomes_an_inline_style_in_kml_byte_order(self):
        document = _document()
        _first_placemark(document)["color"] = "#0f9f95"

        (style,) = _styles_of_first_placemark(document)

        # `#0f9f95` es r=0f g=9f b=95 -> KML `aabbggrr` = ff 95 9f 0f.
        assert style.findtext("k:LineStyle/k:color", namespaces=NS) == "ff959f0f"
        assert style.findtext("k:IconStyle/k:color", namespaces=NS) == "ff959f0f"
        assert style.findtext("k:PolyStyle/k:color", namespaces=NS) == "26959f0f"

    def test_no_colour_means_no_style_is_invented(self):
        document = _document()

        assert _styles_of_first_placemark(document) == []

    def test_a_colour_replaces_the_inline_style_the_file_came_with(self):
        document = _document()
        placemark = _first_placemark(document)
        placemark["extras"] = [
            '<Style xmlns="http://www.opengis.net/kml/2.2">'
            "<LineStyle><color>ff0000ff</color></LineStyle></Style>",
            '<Snippet xmlns="http://www.opengis.net/kml/2.2">kept</Snippet>',
        ]
        placemark["color"] = "#00ff00"

        root = etree.fromstring(build_kml_bytes(document))
        first = root.find(".//k:Placemark", NS)

        # Un solo StyleSelector (el del usuario) y el resto de los extras intacto.
        assert len(first.findall("k:Style", NS)) == 1
        assert (
            first.findtext("k:Style/k:LineStyle/k:color", namespaces=NS) == "ff00ff00"
        )
        assert first.findtext("k:Snippet", namespaces=NS) == "kept"

    def test_without_a_colour_the_original_style_survives(self):
        document = _document()
        _first_placemark(document)["extras"] = [
            '<Style xmlns="http://www.opengis.net/kml/2.2">'
            "<LineStyle><color>ff0000ff</color></LineStyle></Style>"
        ]

        (style,) = _styles_of_first_placemark(document)

        assert style.findtext("k:LineStyle/k:color", namespaces=NS) == "ff0000ff"


def test_the_colour_does_not_break_the_round_trip():
    """Parse no lee el color (no hay de dónde): el viaje de ida y vuelta de un
    documento sin colores sigue siendo un punto fijo."""
    document = _document()
    again = parse_kml_bytes(build_kml_bytes(copy.deepcopy(document)))

    assert [p.get("name") for p in canonical.iter_placemarks(again)] == [
        p.get("name") for p in canonical.iter_placemarks(document)
    ]


# ── El lado del navegador ────────────────────────────────────────────────────
#
# Como en `test_lv277`: no hay infraestructura de tests de JavaScript, así que se
# ejecuta el módulo real (`doc.js`, sin Leaflet ni DOM) en Node.

GEO_JS = Path(settings.BASE_DIR) / "static" / "js" / "geo"
NODE = shutil.which("node")


def _collect_features(tmp_path, doc):
    if NODE is None:
        if os.environ.get("CI"):
            pytest.fail("node no está disponible en el CI")
        pytest.skip("node no está disponible en este equipo")
    module = tmp_path / "doc.mjs"
    module.write_text((GEO_JS / "doc.js").read_text(encoding="utf-8"), encoding="utf-8")
    script = tmp_path / "run.mjs"
    script.write_text(
        'import { collectFeatures } from "./doc.mjs";\n'
        f"console.log(JSON.stringify(collectFeatures({json.dumps(doc)})));\n"
    )
    out = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(out.stdout)


def _placemark(uid, color=None):
    node = {
        "kind": "placemark",
        "uid": uid,
        "name": uid,
        "geometry": {"type": "Point", "coordinates": [-68.9, -22.3]},
    }
    if color:
        node["color"] = color
    return node


def test_the_renderer_receives_the_chosen_colour(tmp_path):
    doc = {"children": [_placemark("a", "#ff0000"), _placemark("b")]}

    items = _collect_features(tmp_path, doc)

    assert [(i["uid"], i["color"]) for i in items] == [("a", "#ff0000"), ("b", None)]


class TestWiring:
    MAIN = (GEO_JS / "main.js").read_text(encoding="utf-8")
    PANEL = (GEO_JS / "panel.js").read_text(encoding="utf-8")

    def test_the_panel_draws_a_colour_picker_that_reports_changes(self):
        assert 'swatch.type = "color"' in self.PANEL
        assert "opts.onColor(node.uid" in self.PANEL

    def test_the_editor_applies_the_colour_to_the_pin_of_a_circle(self):
        """Recolorear el anillo recolorea su centro: el mismo emparejamiento que
        decide cuál punto es su centro (`circles.js`)."""
        assert "onColor," in self.MAIN
        assert "pairCircleCenters(doc).get(uid)" in self.MAIN

    def test_the_layer_uses_the_item_colour_unless_one_is_forced(self):
        assert "forcedColor || item.color" in self.MAIN

    def test_the_picker_label_comes_from_the_server(self):
        from apps.geo import views

        source = Path(views.__file__).read_text(encoding="utf-8")
        assert '"layerColor": _("Layer color")' in source
        assert "labels.layerColor" in self.PANEL
