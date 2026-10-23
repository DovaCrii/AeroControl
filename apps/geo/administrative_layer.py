"""La capa «Límites administrativos» del mapa de espacio aéreo (LV-367, fase 6).

Función pura sobre `apps/geo/data/comunas.txt` (BCN: 346 comunas, 246.930 vértices en el archivo): genera
dos niveles simplificados con Douglas-Peucker y coordenadas a 3 decimales, y sirve de padrón para decir en
qué comuna o región se mira. Sin base de datos, sin HTTP y sin dependencias nuevas.

* **LOD 1** (tolerancia 0,02°, objetivo <= 300 KB sin comprimir) para el zoom <= 7 y **LOD 2** (0,005°,
  objetivo <= 1,1 MB) para el zoom >= 8. Lo vigilan los tests de peso.
* **Referencial.** La fuente (BCN) dice que su cartografía es referencial, y el archivo ya viene simplificado
  a 0,001° (~111 m). Lo que se dibuja es una simplificación más; lo que se CALCULA («qué zonas toca esta
  comuna») usa los anillos completos del archivo, no estos. Se rotula «referencial BCN, ±111 m».
* **Rendijas.** Sólo 26.534 de 212.478 vértices son compartidos entre comunas vecinas (medido sobre el
  archivo), así que simplificar cada comuna por separado abre rendijas y solapes de hasta ~550 m en LOD 1.
  Es un defecto de dibujo conocido y no de datos; no hay topología compartida que lo evite sin una
  dependencia de geometría (shapely/GDAL). Un islote menor que la tolerancia desaparece en ese nivel.
* **Sin polígonos degenerados.** Un anillo que tras simplificar y redondear queda con menos de 3 vértices o
  con área cero se descarta; si una comuna se quedara sin anillos conserva el mayor, simplificado con la
  mitad de la tolerancia las veces que haga falta. La simplificación NO garantiza ausencia de
  autointersecciones (Douglas-Peucker no la garantiza); el dibujo es de relleno par-impar y las tolera.
* **Regiones.** No hay polígonos de región en el repositorio y disolver sin shapely no es razonable: una
  región se realza rellenando sus comunas sin trazo interno. La alternativa es convertir una vez la capa
  «regiones» de BCN (no verificada: no se sabe si su geometría coincide con la de comunas).
* **«Zona sin demarcar»** (código `0`) es territorio que BCN no asigna a ninguna comuna ni región. Se rotula
  así y nunca como región: no entra en la lista de regiones.
* **Datos globales, sin tenant:** es cartografía pública de referencia, igual para todos.
"""

import hashlib
import json
import math
from functools import lru_cache

from .administrative import DATA_FILE, _comunas

# nivel -> tolerancia en grados (lat/lon planos, sin corregir por el coseno: así se midió el peso).
LODS = {1: 0.02, 2: 0.005}
DECIMALS = 3
ALGORITHM_VERSION = "dp1"
UNDEMARCATED_CODE = "0"
SOURCE_NAME = "Biblioteca del Congreso Nacional de Chile (BCN)"
# El archivo trae los anillos simplificados a 0,001°: ~111 m. Se dice tal cual en pantalla.
FILE_TOLERANCE_M = 111


# ---------------------------------------------------------------------------
# Douglas-Peucker
# ---------------------------------------------------------------------------


def _segment_distance(p, a, b):
    """Distancia (en grados, plano) del punto `p` al segmento `ab`; puntos como (lat, lon)."""
    dy, dx = b[0] - a[0], b[1] - a[1]
    length_sq = dy * dy + dx * dx
    if length_sq == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dy + (p[1] - a[1]) * dx) / length_sq))
    return math.hypot(p[0] - (a[0] + t * dy), p[1] - (a[1] + t * dx))


def douglas_peucker(points, tolerance):
    """Polilínea abierta simplificada; conserva siempre el primer y el último punto.

    Iterativo (una comuna llega a decenas de miles de vértices: la recursión no alcanza)."""
    if len(points) < 3 or tolerance <= 0:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        far, far_distance = -1, tolerance
        for i in range(first + 1, last):
            d = _segment_distance(points[i], points[first], points[last])
            if d > far_distance:
                far, far_distance = i, d
        if far != -1:
            keep[far] = True
            stack.append((first, far))
            stack.append((far, last))
    return [p for p, kept in zip(points, keep, strict=True) if kept]


def ring_area(ring):
    """Área con signo (shoelace, grados²) de un anillo abierto de (lat, lon)."""
    total = 0.0
    previous = ring[-1]
    for current in ring:
        total += previous[1] * current[0] - current[1] * previous[0]
        previous = current
    return total / 2.0


def _open(ring):
    return ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring)


def _quantize(ring, decimals):
    """Redondea y quita repetidos consecutivos (incluido el cierre)."""
    out = []
    for lat, lon in ring:
        point = (round(lat, decimals), round(lon, decimals))
        if not out or point != out[-1]:
            out.append(point)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def simplify_ring(ring, tolerance, decimals=DECIMALS):
    """Un anillo simplificado y redondeado, abierto, o `None` si queda degenerado (< 3 vértices o área 0).

    Un anillo no tiene extremos: se ancla en su primer vértice y en el más lejano a él, y se simplifica
    cada mitad por separado, para que el resultado no dependa de dónde empezó el archivo."""
    points = _open(ring)
    if len(points) < 3:
        return None
    far = max(
        range(1, len(points)),
        key=lambda i: _segment_distance(points[i], points[0], points[0]),
    )
    half_a = douglas_peucker(points[: far + 1], tolerance)
    half_b = douglas_peucker(points[far:] + [points[0]], tolerance)
    simplified = _quantize(half_a[:-1] + half_b[:-1], decimals)
    if len(simplified) < 3 or ring_area(simplified) == 0:
        return None
    return simplified


def simplify_rings(rings, tolerance, decimals=DECIMALS):
    """Los anillos de una comuna simplificados; nunca una lista vacía (conserva el anillo mayor)."""
    out = [s for s in (simplify_ring(r, tolerance, decimals) for r in rings) if s]
    if out:
        return out
    biggest = max(rings, key=lambda r: abs(ring_area(_open(r))))
    attempt = tolerance
    while attempt > 1e-6:
        attempt /= 2
        kept = simplify_ring(biggest, attempt, decimals)
        if kept:
            return [kept]
    return [_quantize(_open(biggest), decimals)]


# ---------------------------------------------------------------------------
# El padrón y la capa
# ---------------------------------------------------------------------------


def region_code(commune_code):
    """El código de región de una comuna BCN (`13101` -> `r13`, `1101` -> `r1`); `None` si no tiene."""
    if commune_code == UNDEMARCATED_CODE:
        return None
    return "r" + commune_code[:-3]


@lru_cache(maxsize=1)
def file_digest():
    """sha256 del archivo de datos: es la mitad del ETag (la otra es la versión de la simplificación)."""
    return hashlib.sha256(DATA_FILE.read_bytes()).hexdigest()


def _bbox_lonlat(entry):
    min_lat, min_lon, max_lat, max_lon = entry["bbox"]
    return [
        round(min_lon, DECIMALS),
        round(min_lat, DECIMALS),
        round(max_lon, DECIMALS),
        round(max_lat, DECIMALS),
    ]


@lru_cache(maxsize=1)
def regions():
    """`[{code, name, communes: [códigos], bbox}]` sin «Zona sin demarcar», por nombre."""
    grouped = {}
    for entry in _comunas():
        code = region_code(entry["code"])
        if code is None:
            continue
        item = grouped.setdefault(
            code, {"code": code, "name": entry["region"], "communes": [], "bbox": None}
        )
        item["communes"].append(entry["code"])
        box = _bbox_lonlat(entry)
        item["bbox"] = (
            box
            if item["bbox"] is None
            else [
                min(item["bbox"][0], box[0]),
                min(item["bbox"][1], box[1]),
                max(item["bbox"][2], box[2]),
                max(item["bbox"][3], box[3]),
            ]
        )
    return sorted(grouped.values(), key=lambda r: r["name"])


def search_index():
    """El padrón para el buscador: comunas, regiones y «Zona sin demarcar», con su encuadre.

    Sin geometría (pesa unos pocos KB): sirve para buscar con la capa apagada."""
    entries = [
        {
            "code": entry["code"],
            "name": entry["comuna"],
            "kind": "undemarcated" if entry["code"] == UNDEMARCATED_CODE else "commune",
            "region": entry["region"] if entry["code"] != UNDEMARCATED_CODE else "",
            "bbox": _bbox_lonlat(entry),
        }
        for entry in _comunas()
    ]
    entries.extend(
        {
            "code": r["code"],
            "name": r["name"],
            "kind": "region",
            "region": "",
            "bbox": r["bbox"],
        }
        for r in regions()
    )
    return entries


def _lonlat(ring):
    return [[lon, lat] for lat, lon in ring]


@lru_cache(maxsize=len(LODS))
def build_layer(lod):
    """El dict de la capa en el nivel `lod` (1 ó 2). Pensado para servirse como JSON."""
    tolerance = LODS[lod]
    communes = []
    for entry in _comunas():
        code = entry["code"]
        communes.append(
            {
                "code": code,
                "name": entry["comuna"],
                "region": region_code(code),
                "bbox": _bbox_lonlat(entry),
                "rings": [
                    _lonlat(r) for r in simplify_rings(entry["rings"], tolerance)
                ],
            }
        )
    return {
        "lod": lod,
        "tolerance_deg": tolerance,
        "decimals": DECIMALS,
        "source": SOURCE_NAME,
        "regions": [
            {"code": r["code"], "name": r["name"], "communes": r["communes"]}
            for r in regions()
        ],
        "communes": communes,
    }


def dumps(payload):
    """JSON compacto con `<`, `>` y `&` escapados (inerte aunque alguien lo incruste en HTML)."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


@lru_cache(maxsize=len(LODS))
def layer_bytes(lod):
    return dumps(build_layer(lod)).encode("utf-8")


@lru_cache(maxsize=len(LODS))
def layer_etag(lod):
    """sha256 del archivo de datos + versión de la simplificación (algoritmo y tolerancia)."""
    version = f"{ALGORITHM_VERSION}:lod{lod}:tol{LODS[lod]}:dec{DECIMALS}"
    digest = hashlib.sha256(f"{file_digest()}|{version}".encode()).hexdigest()
    return f'"{digest}"'


# ---------------------------------------------------------------------------
# Una comuna o región, con sus anillos COMPLETOS (para calcular pertenencia)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=16)
def area(code):
    """`{code, name, kind, region, communes, parts}` de una comuna, una región (`r13`) o la zona sin demarcar.

    `parts` es una lista de partes (una por comuna); cada parte, la lista de anillos del archivo (NO los
    simplificados) en `[lon, lat]`. Una región junta las partes de todas sus comunas. `None` si el código
    no existe. El resultado se comparte entre llamadas: no se modifica."""
    code = str(code)
    entries = _comunas()
    if code.startswith("r"):
        members = [e for e in entries if region_code(e["code"]) == code]
        if not members:
            return None
        return {
            "code": code,
            "name": members[0]["region"],
            "kind": "region",
            "region": members[0]["region"],
            "communes": len(members),
            "parts": [[_lonlat(_open(r)) for r in e["rings"]] for e in members],
        }
    for entry in entries:
        if entry["code"] == code:
            undemarcated = code == UNDEMARCATED_CODE
            return {
                "code": code,
                "name": entry["comuna"],
                "kind": "undemarcated" if undemarcated else "commune",
                "region": "" if undemarcated else entry["region"],
                "communes": 1,
                "parts": [[_lonlat(_open(r)) for r in entry["rings"]]],
            }
    return None
