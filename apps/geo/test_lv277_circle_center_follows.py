"""LV-277: al mover una circunferencia, su centro la acompaña.

Pedido del usuario el 2026-10-06, con una captura del editor: *«al momento de mover
una circunferencia el centro se mueva con ella, o cuando finalice de mover la siga»*.

Una circunferencia dibujada son **dos** elementos sueltos: el anillo y un punto
«Centro» (`LV-202`). Sin vínculo entre ellos, arrastrar el anillo dejaba el centro
donde estaba, y la hoja de SIGO —que copia el centro— quedaba con una coordenada que
ya no era la del círculo.

**Cómo se prueba, y por qué en Node**: el repositorio no tiene infraestructura de tests
de JavaScript (`test_lv202_drawn_circle.py` lo explica), y lo que importa acá es una
decisión —*qué punto es el centro de qué anillo*— que el servidor ya toma en
`split_sections`. Se **ejecuta el módulo real** (`static/js/geo/circles.js`, sin Leaflet
ni DOM) en Node y se cruza contra el servidor: si los dos discrepan, el centro que se
mueve en el mapa no sería el que la hoja de SIGO copia.

Se copia a un `.mjs` temporal para importarlo: así no depende de cómo la versión de
Node del equipo trate un `.js` sin `package.json`.
"""

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

from apps.geo.sections import (
    EARTH_RADIUS_KM,
    MAX_RADIUS_DEVIATION,
    split_sections,
)
from apps.geo.test_lv202_drawn_circle import _circle_ring

GEO_JS = Path(settings.BASE_DIR) / "static" / "js" / "geo"
NODE = shutil.which("node")


def _need_node():
    if NODE is None:
        # En el CI Node viene en el runner: que falte ahí es un fallo, no un salto
        # silencioso que deje la prueba sin correr y nadie lo note.
        if os.environ.get("CI"):
            pytest.fail("node no está disponible en el CI")
        pytest.skip("node no está disponible en este equipo")


@pytest.fixture
def js(tmp_path):
    """Ejecuta una expresión contra `circles.js` y devuelve su resultado como JSON."""
    _need_node()
    module = tmp_path / "circles.mjs"
    module.write_text((GEO_JS / "circles.js").read_text(encoding="utf-8"))

    def run(expression, **data):
        script = (
            f"import * as c from {json.dumps(module.as_uri())};\n"
            f"const data = {json.dumps(data)};\n"
            f"console.log(JSON.stringify({expression}));\n"
        )
        done = subprocess.run(
            [NODE, "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


LAT, LON, RADIUS = -22.3, -68.9, 300.0


def _placemark(uid, geometry, name=""):
    return {"kind": "placemark", "uid": uid, "name": name, "geometry": geometry}


def _ring_node(uid, lat=LAT, lon=LON, radius=RADIUS):
    ring = _circle_ring(lat, lon, radius, 64)
    return _placemark(uid, {"type": "Polygon", "coordinates": [ring]})


def _point_node(uid, lat=LAT, lon=LON, name="Centro"):
    return _placemark(uid, {"type": "Point", "coordinates": [lon, lat]}, name)


def _doc(*nodes):
    return {"schema_version": 1, "children": list(nodes)}


def _pairs(js, doc):
    return js("Object.fromEntries(c.pairCircleCenters(data.doc))", doc=doc)


class TestWhichPointIsTheCenter:
    def test_the_pin_drawn_with_the_circle_is_its_center(self, js):
        doc = _doc(_ring_node("ring"), _point_node("pin"))

        assert _pairs(js, doc) == {"ring": "pin"}

    def test_the_server_pairs_the_same_point_with_the_same_ring(self, js):
        """El cruce que importa: lo que se mueve en el mapa es lo que SIGO copia."""
        doc = _doc(
            _ring_node("a", lat=-22.3, lon=-68.9),
            _point_node("pa", lat=-22.3, lon=-68.9),
            _ring_node("b", lat=-22.31, lon=-68.91),
            _point_node("pb", lat=-22.31, lon=-68.91),
        )

        server = {
            section.circle["uid"]: section.point["uid"]
            for section in split_sections(doc)
            if section.circle is not None and section.point is not None
        }

        assert server == {"a": "pa", "b": "pb"}
        assert _pairs(js, doc) == server

    def test_two_circles_with_coincident_points_each_keep_their_own(self, js):
        """La lección del KMZ real de MLP: con «el punto más cercano de cada anillo»
        los dos círculos se disputaban el mismo y uno quedaba huérfano."""
        doc = _doc(
            _ring_node("a", lat=-22.3, lon=-68.9),
            _ring_node("b", lat=-22.3, lon=-68.9001),
            _point_node("pa", lat=-22.3, lon=-68.9),
            _point_node("pb", lat=-22.3, lon=-68.9001),
        )

        pairs = _pairs(js, doc)

        assert pairs == {"a": "pa", "b": "pb"}
        assert len(set(pairs.values())) == 2

    def test_a_point_outside_the_circle_is_not_dragged_along(self, js):
        """El servidor **sí** lo empareja (hasta 3 radios) y el navegador **no**:
        acá el emparejamiento se arrastra, y mover el punto de otra faena que quedó
        cerca porque alguien movió un círculo vecino sería cambiar un dato que nadie
        tocó."""
        far = LAT + (2 * RADIUS) / 111_195  # a dos radios al norte
        doc = _doc(_ring_node("ring"), _point_node("pin", lat=far))

        server_pairs = [
            section
            for section in split_sections(doc)
            if section.circle is not None and section.point is not None
        ]
        assert len(server_pairs) == 1  # el servidor lo reclama
        assert _pairs(js, doc) == {}  # el navegador no lo mueve

    def test_a_rectangle_has_no_center_to_follow(self, js):
        rectangle = [
            [LON - 0.003, LAT - 0.001],
            [LON + 0.003, LAT - 0.001],
            [LON + 0.003, LAT + 0.001],
            [LON - 0.003, LAT + 0.001],
            [LON - 0.003, LAT - 0.001],
        ]
        doc = _doc(
            _placemark("rect", {"type": "Polygon", "coordinates": [rectangle]}),
            _point_node("pin"),
        )

        assert _pairs(js, doc) == {}

    def test_an_open_line_is_a_path_and_not_a_ring(self, js):
        ring = _circle_ring(LAT, LON, RADIUS, 64)[:-1]  # sin cerrar
        doc = _doc(
            _placemark("path", {"type": "LineString", "coordinates": ring}),
            _point_node("pin"),
        )

        assert _pairs(js, doc) == {}

    def test_a_closed_line_string_counts_as_a_ring(self, js):
        """Así exporta Trimble los círculos de CC 738 (`R10.4`)."""
        ring = _circle_ring(LAT, LON, RADIUS, 64)
        doc = _doc(
            _placemark("trimble", {"type": "LineString", "coordinates": ring}),
            _point_node("pin"),
        )

        assert _pairs(js, doc) == {"trimble": "pin"}

    def test_points_inside_folders_are_found(self, js):
        doc = _doc(
            {
                "kind": "folder",
                "uid": "f",
                "name": "Faena",
                "children": [_ring_node("ring"), _point_node("pin")],
            }
        )

        assert _pairs(js, doc) == {"ring": "pin"}


class TestMovingTheGeometry:
    def test_it_shifts_every_coordinate_and_keeps_the_altitude(self, js):
        geometry = {"type": "Point", "coordinates": [-68.9, -22.3, 2500.0]}

        moved = js("c.translateGeometry(data.g, 0.001, -0.002)", g=geometry)

        assert moved["coordinates"] == pytest.approx([-68.899, -22.302, 2500.0])

    def test_it_shifts_a_polygon_ring_by_ring(self, js):
        ring = [[0, 0], [1, 0], [1, 1], [0, 0]]
        geometry = {"type": "Polygon", "coordinates": [ring]}

        moved = js("c.translateGeometry(data.g, 10, 20)", g=geometry)

        assert moved["coordinates"][0][1] == [11, 20]
        assert len(moved["coordinates"][0]) == 4

    def test_the_original_is_not_mutated(self, js):
        geometry = {"type": "Point", "coordinates": [1, 2]}

        result = js(
            "(() => { const g = data.g; c.translateGeometry(g, 5, 5); return g; })()",
            g=geometry,
        )

        assert result["coordinates"] == [1, 2]

    def test_the_center_follows_the_ring_by_the_same_distance(self, js):
        """Mover el anillo `d` grados y el centro `d` grados: siguen siendo concéntricos."""
        ring = _circle_ring(LAT, LON, RADIUS, 64)
        pin = [LON, LAT]

        out = js(
            """(() => {
                const moved = c.translateGeometry({type:'Polygon',coordinates:[data.ring]}, 0.01, 0.02);
                const pin = c.translateGeometry({type:'Point',coordinates:data.pin}, 0.01, 0.02);
                const centre = c.ringCentroid(moved.coordinates[0]);
                return {dLat: centre.lat - pin.coordinates[1], dLng: centre.lng - pin.coordinates[0]};
            })()""",
            ring=ring,
            pin=pin,
        )

        assert abs(out["dLat"]) < 1e-9
        assert abs(out["dLng"]) < 1e-9


class TestTheConstantsAgreeWithTheServer:
    def test_the_circle_threshold_is_the_servers(self):
        source = (GEO_JS / "circles.js").read_text(encoding="utf-8")
        found = re.search(r"MAX_RADIUS_DEVIATION\s*=\s*([0-9.]+)", source)
        assert found and float(found.group(1)) == MAX_RADIUS_DEVIATION

    def test_the_earth_radius_is_the_servers(self):
        source = (GEO_JS / "circles.js").read_text(encoding="utf-8")
        found = re.search(r"EARTH_RADIUS_M\s*=\s*([0-9.]+)", source)
        assert found and math.isclose(float(found.group(1)), EARTH_RADIUS_KM * 1000)

    def test_the_measured_radius_matches_the_servers_for_a_drawn_circle(self, js):
        from apps.geo.sections import estimate_radius_m

        ring = _circle_ring(LAT, LON, RADIUS, 64)
        server_radius, server_deviation = estimate_radius_m((LAT, LON), ring)

        out = js("c.radiusStats(c.ringCentroid(data.ring), data.ring)", ring=ring)

        assert out["meanM"] == pytest.approx(server_radius, rel=1e-3)
        assert out["deviation"] == pytest.approx(server_deviation, abs=1e-4)


class TestTheEditorIsWiredToIt:
    """El cableado, a la vista: es lo que un test de Node no alcanza a mirar."""

    EDIT = (GEO_JS / "edit.js").read_text(encoding="utf-8")
    MAIN = (GEO_JS / "main.js").read_text(encoding="utf-8")

    def test_dragging_a_layer_moves_its_center_live_and_saves_it_at_the_end(self):
        assert "pm:dragstart" in self.EDIT
        assert 'layer.on("pm:drag"' in self.EDIT
        assert "pairCircleCenters" in self.EDIT

    def test_the_renderer_hands_the_editor_the_layers_by_uid(self):
        assert re.search(r"wireLayer\([^)]*uidLayers", self.MAIN, re.S)
