"""LV-367 (fase 6): la capa «Límites administrativos» generada desde `apps/geo/data/comunas.txt` (BCN).

Pesos medidos (no estimados) sobre el archivo real del repositorio, que es cartografía pública de BCN:
LOD 1 <= 300 KB y LOD 2 <= 1,1 MB sin comprimir. La simplificación no puede dejar polígonos degenerados
ni comunas vacías, y las rendijas entre comunas vecinas son un límite CONOCIDO y documentado.
"""

import json
from collections import Counter

import pytest

from apps.geo import administrative, administrative_layer as layer

KB = 1024


# ── Douglas-Peucker y anillos ───────────────────────────────────────────────


def test_douglas_peucker_keeps_the_ends_and_drops_what_is_within_tolerance():
    line = [(0.0, 0.0), (0.001, 1.0), (0.0, 2.0), (1.0, 3.0)]
    kept = layer.douglas_peucker(line, 0.01)
    assert kept[0] == line[0] and kept[-1] == line[-1]
    assert (0.001, 1.0) not in kept  # a 0,001 de la recta: dentro de la tolerancia
    assert (0.0, 2.0) in kept  # el giro hacia (1, 3) sí se conserva


def test_douglas_peucker_with_zero_tolerance_changes_nothing():
    line = [(0.0, 0.0), (0.5, 0.1), (1.0, 0.0)]
    assert layer.douglas_peucker(line, 0) == line


def test_a_ring_does_not_depend_on_where_the_file_started_it():
    square = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    shifted = square[2:] + square[:2]
    a = layer.simplify_ring(square + [square[0]], 0.1)
    b = layer.simplify_ring(shifted + [shifted[0]], 0.1)
    assert sorted(a) == sorted(b) == sorted(square)


def test_a_ring_that_collapses_is_dropped_not_served_degenerate():
    sliver = [(0.0, 0.0), (0.0002, 0.5), (0.0, 1.0), (0.0002, 0.5)]
    assert layer.simplify_ring(sliver, 0.02) is None
    assert layer.simplify_ring([(0.0, 0.0), (1.0, 1.0)], 0.02) is None


def test_a_commune_made_only_of_islets_below_the_tolerance_keeps_its_biggest_ring():
    islets = [
        [(0.0, 0.0), (0.0, 0.004), (0.004, 0.004), (0.004, 0.0)],
        [(1.0, 1.0), (1.0, 1.002), (1.002, 1.002), (1.002, 1.0)],
    ]
    out = layer.simplify_rings(islets, 0.02)
    assert len(out) == 1 and len(out[0]) >= 3
    assert abs(layer.ring_area(out[0])) > 0


def test_coordinates_are_rounded_to_three_decimals():
    ring = [
        (0.12345, 0.98765),
        (0.12345, 1.98765),
        (1.12345, 1.98765),
        (1.12345, 0.98765),
    ]
    assert set(layer.simplify_ring(ring, 0)) == {
        (0.123, 0.988),
        (0.123, 1.988),
        (1.123, 1.988),
        (1.123, 0.988),
    }


# ── la capa real ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("lod", "ceiling"), [(1, 300 * KB), (2, 1100 * KB)])
def test_each_level_weighs_what_it_was_designed_to_weigh(lod, ceiling):
    size = len(layer.layer_bytes(lod))
    assert size <= ceiling, f"LOD {lod}: {size / KB:.0f} KB over {ceiling / KB:.0f} KB"
    # ...y no es trivial: un LOD 2 que pesa igual que el 1 no simplifica con su tolerancia.
    assert size > 100 * KB


def test_the_second_level_is_finer_than_the_first():
    first, second = layer.layer_bytes(1), layer.layer_bytes(2)
    assert len(second) > 2 * len(first)


@pytest.mark.parametrize("lod", [1, 2])
def test_every_commune_is_there_with_at_least_one_proper_ring(lod):
    data = layer.build_layer(lod)
    assert len(data["communes"]) == 346
    assert len({c["code"] for c in data["communes"]}) == 346
    for commune in data["communes"]:
        assert commune["rings"], commune["name"]
        for ring in commune["rings"]:
            points = [(lat, lon) for lon, lat in ring]
            assert len(points) >= 3, commune["name"]
            # Ningún vértice repetido en fila (un anillo puede tocarse a sí mismo; eso no es un error).
            assert all(
                a != b for a, b in zip(points, points[1:] + points[:1], strict=True)
            ), commune["name"]
            assert layer.ring_area(points) != 0, commune["name"]


@pytest.mark.parametrize("lod", [1, 2])
def test_coordinates_have_at_most_three_decimals_and_stay_inside_the_bbox(lod):
    for commune in layer.build_layer(lod)["communes"]:
        min_lon, min_lat, max_lon, max_lat = commune["bbox"]
        for ring in commune["rings"]:
            for lon, lat in ring:
                assert round(lon, 3) == lon and round(lat, 3) == lat
                # La simplificación nunca saca un vértice del recuadro original (mas el redondeo).
                assert min_lon - 0.001 <= lon <= max_lon + 0.001, commune["name"]
                assert min_lat - 0.001 <= lat <= max_lat + 0.001, commune["name"]


def test_there_are_sixteen_regions_and_the_undemarcated_zone_is_not_one_of_them():
    regions = layer.regions()
    assert len(regions) == 16
    assert all(r["code"].startswith("r") for r in regions)
    assert not any("demarcar" in r["name"].lower() for r in regions)
    assert (
        sum(len(r["communes"]) for r in regions) == 345
    )  # 346 menos la zona sin demarcar
    assert layer.region_code(layer.UNDEMARCATED_CODE) is None
    # Una comuna pertenece a UNA región: el código de región sale del código de la comuna.
    names_by_code = {}
    for entry in administrative._comunas():
        code = layer.region_code(entry["code"])
        if code:
            names_by_code.setdefault(code, set()).add(entry["region"])
    assert all(len(names) == 1 for names in names_by_code.values())


def test_the_undemarcated_zone_is_labelled_as_such_and_never_as_a_region():
    commune = next(c for c in layer.build_layer(1)["communes"] if c["code"] == "0")
    assert commune["name"] == "Zona sin demarcar"
    assert commune["region"] is None
    entry = next(e for e in layer.search_index() if e["code"] == "0")
    assert entry["kind"] == "undemarcated" and entry["region"] == ""
    assert layer.area("0")["kind"] == "undemarcated"


def test_the_search_index_holds_names_and_frames_but_no_geometry():
    index = layer.search_index()
    kinds = Counter(e["kind"] for e in index)
    assert kinds == {"commune": 345, "undemarcated": 1, "region": 16}
    assert all(len(e["bbox"]) == 4 for e in index)
    assert (
        len(json.dumps(index)) < 120 * KB
    )  # entra en la configuración de la página sin pesar
    assert all("rings" not in e and "geometry" not in e for e in index)


def test_the_json_is_inert_markup_wise():
    text = layer.dumps({"name": "<script>&</script>"})
    assert "<" not in text and ">" not in text and "&" not in text
    assert json.loads(text) == {"name": "<script>&</script>"}
    assert b"<" not in layer.layer_bytes(1)


# ── ETag ────────────────────────────────────────────────────────────────────


def test_the_etag_is_the_file_hash_plus_the_simplification_version(monkeypatch):
    first, second = layer.layer_etag(1), layer.layer_etag(2)
    assert first != second and first.startswith('"') and first.endswith('"')
    layer.layer_etag.cache_clear()
    monkeypatch.setattr(layer, "ALGORITHM_VERSION", "dp-next")
    assert (
        layer.layer_etag(1) != first
    )  # cambiar el algoritmo invalida lo que el navegador guardó
    layer.layer_etag.cache_clear()
    monkeypatch.setitem(layer.LODS, 1, 0.03)
    assert layer.layer_etag(1) != first  # y cambiar la tolerancia también
    monkeypatch.undo()
    layer.layer_etag.cache_clear()
    assert layer.layer_etag(1) == first  # restaurado, vuelve a ser el mismo
    assert layer.file_digest() in (
        __import__("hashlib").sha256(layer.DATA_FILE.read_bytes()).hexdigest(),
    )


# ── las rendijas, documentadas y medidas ────────────────────────────────────


def test_the_gaps_between_neighbours_are_documented_and_the_measure_still_holds():
    doc = layer.__doc__
    assert "rendijas" in doc and "26.534" in doc and "212.478" in doc and "550 m" in doc
    # La cifra del docstring es una medida del archivo: si el archivo cambia, el aviso se actualiza.
    owners = {}
    for entry in administrative._comunas():
        for ring in entry["rings"]:
            for vertex in ring:
                owners.setdefault(vertex, set()).add(entry["code"])
    shared = sum(1 for codes in owners.values() if len(codes) > 1)
    assert len(owners) == 212478
    assert shared == 26534
    assert (
        shared / len(owners) < 0.15
    )  # la mayoría de los vértices NO se comparte: de ahí las rendijas
