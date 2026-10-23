"""Geometría pura del espacio aéreo (LV-357, fase 2).

Funciones sin modelos ni ORM sobre «features» GeoJSON simplificados::

    {"type": "Feature", "properties": {"kind": "restricted", "code": "SC-R41"},
     "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...], ...]}}

Convenciones, para que nadie las tenga que adivinar:

* Las coordenadas GeoJSON van en ``[lon, lat]``; los argumentos sueltos de
  estas funciones van en ``lat, lon`` (el orden humano, como `haversine_km`).
* Distancias en kilómetros; `km_to_nm` / `nm_to_km` para millas náuticas.
* Un punto sobre el borde de un polígono cuenta como **dentro** (el piloto
  que está en el límite está en la zona).
* La distancia a un borde se calcula en un plano local centrado en el punto
  (suficiente a las escalas de operación, ~decenas de km); las zonas muy
  grandes (FIR) no son para este cálculo.
"""

import math

from .administrative import _in_ring
from .enclosing import METERS_PER_DEGREE, _project
from .sections import haversine_km

KM_PER_NM = 1.852
# Tolerancia para decir «sobre el borde»: medio metro.
EDGE_TOLERANCE_KM = 0.0005

AERODROME_KINDS = ("aerodrome", "airport")
POINT_KINDS = ("aerodrome", "airport", "airstrip")


def km_to_nm(km):
    return km / KM_PER_NM


def nm_to_km(nm):
    return nm * KM_PER_NM


def distance_km(lat1, lon1, lat2, lon2):
    return haversine_km(lat1, lon1, lat2, lon2)


def distance_nm(lat1, lon1, lat2, lon2):
    return km_to_nm(haversine_km(lat1, lon1, lat2, lon2))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Rumbo inicial (grados verdaderos, 0 <= r < 360) del punto 1 al 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        dlambda
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


# ---------------------------------------------------------------------------
# Piezas de una geometría
# ---------------------------------------------------------------------------


def _parts(geometry):
    """Las piezas de un `GeometryCollection` (un `MultiGeometry` de KML), o []. Antes se ignoraban:
    una zona con su punto de rótulo (SC-P29) no la encontraba «¿qué hay cerca?» (LV-363)."""
    if (geometry or {}).get("type") == "GeometryCollection":
        return geometry.get("geometries") or []
    return []


def _polygons(geometry):
    """Lista de polígonos (cada uno, lista de anillos [lon, lat])."""
    kind = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates") or []
    if kind == "Polygon":
        return [coords]
    if kind == "MultiPolygon":
        return list(coords)
    return [polygon for part in _parts(geometry) for polygon in _polygons(part)]


def _lines(geometry):
    """Lista de polilíneas ([lon, lat]...)."""
    kind = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates") or []
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return list(coords)
    return [line for part in _parts(geometry) for line in _lines(part)]


def _points(geometry):
    kind = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates") or []
    if kind == "Point":
        return [coords] if coords else []
    if kind == "MultiPoint":
        return list(coords)
    return [point for part in _parts(geometry) for point in _points(part)]


def _all_positions(geometry):
    positions = list(_points(geometry))
    for line in _lines(geometry):
        positions.extend(line)
    for polygon in _polygons(geometry):
        for ring in polygon:
            positions.extend(ring)
    return positions


def bbox_of(geometry):
    """(min_lon, min_lat, max_lon, max_lat) o None si no hay posiciones."""
    positions = _all_positions(geometry)
    if not positions:
        return None
    lons = [p[0] for p in positions]
    lats = [p[1] for p in positions]
    return (min(lons), min(lats), max(lons), max(lats))


def bbox_near(bbox, lat, lon, margin_km=0.0):
    """Prefiltro barato: ¿el punto cae en el bbox ensanchado `margin_km`?

    Es sólo un descarte rápido (puede dejar pasar de más, nunca dejar fuera
    algo que esté a <= margin_km)."""
    if bbox is None:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    margin_lat = margin_km * 1000.0 / METERS_PER_DEGREE
    # A latitud alta un grado de longitud mide menos: se ensancha de más.
    cos_lat = max(math.cos(math.radians(min(abs(lat), 89.0))), 0.01)
    margin_lon = margin_lat / cos_lat
    return (
        min_lat - margin_lat <= lat <= max_lat + margin_lat
        and min_lon - margin_lon <= lon <= max_lon + margin_lon
    )


# ---------------------------------------------------------------------------
# Punto y polígono
# ---------------------------------------------------------------------------


def _segment_distance_km(px, py, ax, ay, bx, by):
    """Distancia (en las unidades del plano, metros) de P al segmento AB."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _distance_to_path_km(lat, lon, path, closed=False):
    """Distancia mínima del punto a una polilínea (o anillo si `closed`)."""
    if not path:
        return math.inf
    projected = _project(path, lat, lon)  # el punto queda en (0, 0)
    if len(projected) == 1:
        return math.hypot(*projected[0]) / 1000.0
    pairs = list(zip(projected, projected[1:], strict=False))
    if closed and projected[0] != projected[-1]:
        pairs.append((projected[-1], projected[0]))
    best = min(_segment_distance_km(0.0, 0.0, a[0], a[1], b[0], b[1]) for a, b in pairs)
    return best / 1000.0


def _ring_latlon(ring):
    return [(p[1], p[0]) for p in ring]


def point_in_polygon(lat, lon, rings):
    """`rings` = [exterior, hole, hole...] en [lon, lat]. Borde = dentro."""
    if not rings or len(rings[0]) < 3:
        return False
    if not _in_ring(lat, lon, _ring_latlon(rings[0])):
        # El trazado de rayo es inestable justo en el borde: se confirma.
        return (
            _distance_to_path_km(lat, lon, rings[0], closed=True) <= EDGE_TOLERANCE_KM
        )
    for hole in rings[1:]:
        if len(hole) >= 3 and _in_ring(lat, lon, _ring_latlon(hole)):
            # Dentro del hueco: sólo cuenta si está sobre el borde del hueco.
            return (
                _distance_to_path_km(lat, lon, hole, closed=True) <= EDGE_TOLERANCE_KM
            )
    return True


def point_in_geometry(lat, lon, geometry):
    """¿El punto está dentro de algún polígono de la geometría?"""
    return any(point_in_polygon(lat, lon, polygon) for polygon in _polygons(geometry))


def distance_to_polygon_edge_km(lat, lon, rings):
    """Distancia al borde más cercano (exterior o huecos), esté dentro o no."""
    return min(
        (_distance_to_path_km(lat, lon, ring, closed=True) for ring in rings if ring),
        default=math.inf,
    )


def distance_to_line_km(lat, lon, line):
    return _distance_to_path_km(lat, lon, line, closed=False)


def distance_to_geometry_km(lat, lon, geometry):
    """Distancia del punto a la geometría; 0 si está dentro de un polígono.

    Mínimo entre puntos (haversine), polilíneas y polígonos."""
    best = math.inf
    for point in _points(geometry):
        best = min(best, haversine_km(lat, lon, point[1], point[0]))
    for line in _lines(geometry):
        best = min(best, distance_to_line_km(lat, lon, line))
    for polygon in _polygons(geometry):
        if point_in_polygon(lat, lon, polygon):
            return 0.0
        best = min(best, distance_to_polygon_edge_km(lat, lon, polygon))
    return best


# ---------------------------------------------------------------------------
# Comparar dos formas (cruce AIP / Google, LV-361)
# ---------------------------------------------------------------------------


def vertices_of(geometry):
    """Los vértices ``[lon, lat]`` de una geometría; un anillo cerrado no repite el primero."""
    vertices = [list(p) for p in _points(geometry)]
    for line in _lines(geometry):
        vertices.extend(list(p) for p in line)
    for polygon in _polygons(geometry):
        for ring in polygon:
            closed = len(ring) > 1 and list(ring[0]) == list(ring[-1])
            vertices.extend(list(p) for p in (ring[:-1] if closed else ring))
    return vertices


def boundary_distance_km(lat, lon, geometry):
    """Distancia del punto al BORDE de la geometría (puntos, líneas y anillos).

    A diferencia de `distance_to_geometry_km`, un punto dentro de un polígono no da 0: sirve para
    medir cuánto se separa un vértice de la otra forma, esté dentro o fuera de ella."""
    best = math.inf
    for point in _points(geometry):
        best = min(best, haversine_km(lat, lon, point[1], point[0]))
    for line in _lines(geometry):
        best = min(best, distance_to_line_km(lat, lon, line))
    for polygon in _polygons(geometry):
        best = min(best, distance_to_polygon_edge_km(lat, lon, polygon))
    return best


def vertex_distances_m(geometry, other):
    """Metros de cada vértice de `geometry` al borde de `other`, de menor a mayor.

    Lista vacía si alguna de las dos no tiene posiciones: sin forma no hay distancia que inventar."""
    if not _all_positions(other):
        return []
    return sorted(
        boundary_distance_km(lat, lon, other) * 1000.0
        for lon, lat in vertices_of(geometry)
    )


# ---------------------------------------------------------------------------
# Círculos
# ---------------------------------------------------------------------------


def circle_intersects_circle(lat1, lon1, radius1_km, lat2, lon2, radius2_km):
    """¿Se tocan dos círculos (tangentes cuentan)?"""
    return haversine_km(lat1, lon1, lat2, lon2) <= radius1_km + radius2_km


def circle_intersects_geometry(lat, lon, radius_km, geometry):
    """¿El círculo (centro, radio) toca la geometría?

    En un polígono incluye el caso de que el borde cruce el círculo **sin**
    contener el centro, y el de que el polígono quede entero dentro."""
    return distance_to_geometry_km(lat, lon, geometry) <= radius_km


# ---------------------------------------------------------------------------
# «Qué hay cerca de aquí»
# ---------------------------------------------------------------------------


def _kind(feature):
    return (feature.get("properties") or {}).get("kind")


def _entry(feature, lat, lon, distance):
    geometry = feature.get("geometry") or {}
    points = _points(geometry)
    bearing = None
    if geometry.get("type") == "Point" and points:
        bearing = bearing_deg(lat, lon, points[0][1], points[0][0])
    return {
        "feature": feature,
        "distance_km": distance,
        "distance_nm": km_to_nm(distance),
        "bearing_deg": bearing,
    }


def nearby(
    lat,
    lon,
    features,
    within_km=10.0,
    aerodromes=5,
    aerodrome_kinds=AERODROME_KINDS,
):
    """Qué hay alrededor de un punto.

    Devuelve un dict con tres listas:

    * ``containing``: zonas (polígonos) que contienen el punto.
    * ``within``: zonas que no lo contienen pero están a <= `within_km`,
      de la más cercana a la más lejana.
    * ``aerodromes``: los `aerodromes` puntos de `aerodrome_kinds` más
      cercanos, sin límite de distancia, con distancia en km y NM y rumbo.

    Las pistas chicas (``airstrip``) no son zonas ni aeródromos: se omiten
    salvo que se pidan en `aerodrome_kinds`."""
    containing, within, points = [], [], []
    for feature in features:
        geometry = feature.get("geometry") or {}
        kind = _kind(feature)
        if kind in aerodrome_kinds and geometry.get("type") == "Point":
            coords = geometry.get("coordinates")
            if coords:
                points.append(
                    _entry(
                        feature, lat, lon, haversine_km(lat, lon, coords[1], coords[0])
                    )
                )
            continue
        if kind in POINT_KINDS:
            continue
        if not bbox_near(bbox_of(geometry), lat, lon, within_km):
            continue
        if point_in_geometry(lat, lon, geometry):
            containing.append(_entry(feature, lat, lon, 0.0))
            continue
        distance = distance_to_geometry_km(lat, lon, geometry)
        if distance <= within_km:
            within.append(_entry(feature, lat, lon, distance))
    within.sort(key=lambda e: e["distance_km"])
    points.sort(key=lambda e: e["distance_km"])
    return {
        "containing": containing,
        "within": within,
        "aerodromes": points[: max(aerodromes, 0)],
    }


# ---------------------------------------------------------------------------
# Pertenencia a una comuna o región (LV-367, fase 6)
# ---------------------------------------------------------------------------
#
# El «área» es una lista de PARTES (una por comuna); cada parte, una lista de anillos [lon, lat] que se
# leen con la regla par-impar (islas y huecos, como `administrative.locate`). Una región es la unión de sus
# comunas: se prueba por parte y se junta con «o», porque dos comunas vecinas se solapan o dejan rendijas
# de hasta ~111 m y un par-impar sobre todo el conjunto contaría el solapamiento como «fuera».
#
# Qué es y qué no es cada resultado, para que nadie lo lea como más de lo que dice:
#   * `geometry_intersects_rings`: recuadro -> vértice en polígono en ambos sentidos -> cruce de aristas.
#     Es exacto sobre los anillos que recibe (no inventa tolerancia).
#   * «contenida» es MUESTREADA: todos los vértices y tres puntos por arista caen dentro del área. Una
#     protuberancia más fina que ese muestreo, o dentro de la rendija de dos comunas, se le puede escapar;
#     por eso la pantalla dice «referencial BCN, ±111 m».


def _box_of(ring):
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lons), min(lats), max(lons), max(lats))


def _boxes_overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _in_box(box, lon, lat):
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def _in_ring_xy(lon, lat, ring):
    """Trazado de rayo sobre un anillo `[lon, lat]` (el mismo algoritmo que `administrative._in_ring`)."""
    inside = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > lat) != (previous[1] > lat):
            crossing = previous[0] + (lat - previous[1]) * (
                current[0] - previous[0]
            ) / (current[1] - previous[1])
            if lon < crossing:
                inside = not inside
        previous = current
    return inside


def _prepare_parts(parts):
    prepared = []
    for rings in parts:
        valid = [ring for ring in rings if len(ring) >= 3]
        if not valid:
            continue
        boxes = [_box_of(ring) for ring in valid]
        box = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        prepared.append((box, valid, boxes))
    return prepared


def _in_part(lon, lat, part):
    box, rings, boxes = part
    if not _in_box(box, lon, lat):
        return False
    inside = False
    for ring, ring_box in zip(rings, boxes, strict=True):
        if _in_box(ring_box, lon, lat) and _in_ring_xy(lon, lat, ring):
            inside = not inside
    return inside


def _orientation(a, b, c):
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    return 0 if value == 0 else (1 if value > 0 else 2)


def _on_segment(a, b, c):
    return min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and min(a[1], c[1]) <= b[
        1
    ] <= max(a[1], c[1])


def _segments_intersect(p1, p2, p3, p4):
    """¿Se tocan los segmentos p1p2 y p3p4? Tocarse en un punto o ser colineales y solaparse cuenta."""
    o1, o2 = _orientation(p1, p2, p3), _orientation(p1, p2, p4)
    o3, o4 = _orientation(p3, p4, p1), _orientation(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(p1, p3, p2))
        or (o2 == 0 and _on_segment(p1, p4, p2))
        or (o3 == 0 and _on_segment(p3, p1, p4))
        or (o4 == 0 and _on_segment(p3, p2, p4))
    )


def _edges(geometry):
    """Las aristas de una geometría con su recuadro: anillos de polígono (cerrados) y polilíneas."""
    pairs = []
    for polygon in _polygons(geometry):
        for ring in polygon:
            if len(ring) >= 2:
                pairs.extend(zip(ring, ring[1:] + ring[:1], strict=True))
    for line in _lines(geometry):
        pairs.extend(zip(line, line[1:], strict=False))
    return [
        (a, b, (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
        for a, b in pairs
    ]


def _intersects_part(gbox, positions, polygons, edges, part):
    box, rings, boxes = part
    if not _boxes_overlap(gbox, box):
        return False
    # 1. un vértice de la geometría dentro del área
    if any(_in_part(p[0], p[1], part) for p in positions if _in_box(box, p[0], p[1])):
        return True
    # 2. un vértice del área dentro de un polígono de la geometría (el área cabe entera en la zona)
    if polygons:
        for ring, ring_box in zip(rings, boxes, strict=True):
            if not _boxes_overlap(gbox, ring_box):
                continue
            for lon, lat in ring:
                if _in_box(gbox, lon, lat) and any(
                    point_in_polygon(lat, lon, polygon) for polygon in polygons
                ):
                    return True
    # 3. una arista de la geometría cruza una arista del área (sin que ningún vértice esté dentro)
    if edges:
        for ring, ring_box in zip(rings, boxes, strict=True):
            if not _boxes_overlap(gbox, ring_box):
                continue
            for a, b in zip(ring, ring[1:] + ring[:1], strict=True):
                edge_box = (
                    min(a[0], b[0]),
                    min(a[1], b[1]),
                    max(a[0], b[0]),
                    max(a[1], b[1]),
                )
                if not _boxes_overlap(gbox, edge_box):
                    continue
                for c, d, other_box in edges:
                    if _boxes_overlap(edge_box, other_box) and _segments_intersect(
                        a, b, c, d
                    ):
                        return True
    return False


def _geometry_context(geometry):
    gbox = bbox_of(geometry)
    if gbox is None:
        return None
    return (gbox, _all_positions(geometry), _polygons(geometry), _edges(geometry))


def geometry_intersects_rings(geometry, rings):
    """¿La geometría toca el área descrita por `rings` (anillos `[lon, lat]`, regla par-impar)?

    Tres pasos, del más barato al más caro: recuadros que no se tocan (descarte); un vértice de un lado
    dentro del otro, **en ambos sentidos** (la zona dentro del área y el área entera dentro de la zona);
    y, si nada de eso, un cruce de aristas (dos contornos que se atraviesan sin que ningún vértice quede
    del otro lado). Tocarse en el borde cuenta."""
    context = _geometry_context(geometry)
    parts = _prepare_parts([rings])
    if context is None or not parts:
        return False
    return _intersects_part(*context, parts[0])


def _samples(geometry):
    """Vértices y tres puntos por arista (1/4, 1/2, 3/4): lo que se prueba para decir «contenida»."""
    points = list(_all_positions(geometry))
    for a, b, _box in _edges(geometry):
        for t in (0.25, 0.5, 0.75):
            points.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return points


def _within_parts(geometry, prepared):
    return all(
        any(_in_part(lon, lat, part) for part in prepared)
        for lon, lat in _samples(geometry)
    )


def features_in_area(features, parts):
    """Qué zonas y aeródromos hay en un área (`parts`: lista de anillos por comuna).

    Devuelve `[{"feature": ..., "relation": "contained" | "touches"}]` en el orden recibido:

    * un punto de aeródromo (`AERODROME_KINDS`): sólo si cae dentro; relación ``contained``.
    * una zona (cualquier otro tipo con geometría): ``contained`` si TODAS sus muestras caen dentro del
      área, ``touches`` si la toca sin estar contenida, y nada si no la toca.

    Las pistas chicas y las geometrías vacías se omiten. Se calcula contra los anillos completos que
    se reciben; el resultado es referencial (los anillos de BCN vienen a ~111 m)."""
    prepared = _prepare_parts(parts)
    found = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        kind = _kind(feature)
        if kind == "airstrip":
            continue
        if kind in AERODROME_KINDS:
            points = _points(geometry)
            if points and any(
                _in_part(points[0][0], points[0][1], part) for part in prepared
            ):
                found.append({"feature": feature, "relation": "contained"})
            continue
        context = _geometry_context(geometry)
        if context is None:
            continue
        near = [part for part in prepared if _boxes_overlap(context[0], part[0])]
        if not any(_intersects_part(*context, part) for part in near):
            continue
        relation = "contained" if _within_parts(geometry, near) else "touches"
        found.append({"feature": feature, "relation": relation})
    return found
