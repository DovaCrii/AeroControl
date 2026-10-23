"""LV-367 (fase 7): el buscador de comunas y regiones, en Python y en JS, da las MISMAS respuestas.

`airspace-search.js` es un port de `apps/geo/airspace_search.py`; la fase 7 le suma `adminEntries` (y Python
`admin_entries`). Se corren los mismos casos —con tildes, mayúsculas, la eñe y la zona sin demarcar— sobre
el padrón real de `administrative_layer.search_index()` y se exige igualdad entrada por entrada y puntaje
por puntaje.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.geo import administrative_layer as layer
from apps.geo import airspace_search

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

QUERIES = [
    "nuble",
    "ÑUBLE",
    "Ñuble",
    "penalolen",
    "PEÑALOLÉN",
    "region metropolitana",
    "metropolitana de santiago",
    "santiago",
    "San",
    "sin demarcar",
    "Zona sin demarcar",
    "valparaiso",
    "Región de Valparaíso",
    "aysen",
    "o'higgins",
    "bio bio",
    "ñuñoa",
    "Vitacura",
    "zzzz",
    "",
]

SCRIPT = """
const S = require('./static/js/airspace-search.js');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', () => {
  const input = JSON.parse(raw);
  const entries = S.adminEntries(input.index);
  const results = input.queries.map(q => S.searchIndex(q, entries, 20).results.map(r => [r.entry.id, r.score]));
  process.stdout.write(JSON.stringify({ entries, results }));
});
"""


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
def test_the_client_and_the_python_search_agree_on_communes_and_regions():
    index = layer.search_index()
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", SCRIPT],
        input=json.dumps({"index": index, "queries": QUERIES}, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    out = json.loads(result.stdout)
    entries = airspace_search.admin_entries(index)
    assert out["entries"] == entries  # el mismo padrón de entradas, campo por campo
    for query, got in zip(QUERIES, out["results"], strict=True):
        expected = airspace_search.search_index(query, entries, limit=20)["results"]
        assert got == [[r["entry"]["id"], r["score"]] for r in expected], query


def test_accents_and_capitals_do_not_matter_and_the_ids_are_prefixed():
    entries = airspace_search.admin_entries(layer.search_index())
    assert all(e["id"].startswith(airspace_search.ADMIN_ID_PREFIX) for e in entries)
    assert all(e["code"] == "" for e in entries)  # el código BCN no se escribe
    for query in ("nuble", "ÑUBLE", "Ñuble"):
        names = [
            r["entry"]["name"]
            for r in airspace_search.search_index(query, entries)["results"]
        ]
        assert "Región de Ñuble" in names, query
    first = airspace_search.search_index("penalolen", entries)["results"][0]
    assert first["entry"]["name"] == "Peñalolén" and first["score"] == 100


def test_the_undemarcated_zone_is_found_by_its_name_and_is_never_a_region():
    entries = airspace_search.admin_entries(layer.search_index())
    found = airspace_search.search_index("sin demarcar", entries)["results"]
    assert [r["entry"]["kind"] for r in found] == ["undemarcated"]
    assert not any(
        e["kind"] == "region" and "demarcar" in e["name"].lower() for e in entries
    )


def test_a_region_and_a_commune_of_the_same_name_are_both_offered():
    """«Santiago» es una comuna Y está dentro del nombre de una región: se ofrecen las dos, con su tipo."""
    entries = airspace_search.admin_entries(layer.search_index())
    kinds = {
        r["entry"]["kind"]
        for r in airspace_search.search_index("santiago", entries, limit=50)["results"]
    }
    assert {"commune", "region"} <= kinds
