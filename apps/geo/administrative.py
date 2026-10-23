"""LV-141: en qué comuna, provincia y región cae el punto central.

SIGO pide **Comuna** y **Área** como casillas propias, y hasta acá las dos se
tipeaban a mano teniendo el KMZ delante. El área ya salía del nombre del
placemark; la comuna no salía de ninguna parte, porque para saberla hay que
resolver en qué polígono administrativo cae el punto.

**La fuente y su advertencia.** Los límites vienen de la capa vectorial de
comunas de la **Biblioteca del Congreso Nacional** (`apps/geo/data/comunas.txt`,
ver su cabecera): uso libre citando la fuente, y con una salvedad que BCN pone por
escrito y que este módulo hereda — *su cartografía es referencial y no debe usarse
para trabajos que requieran precisión geodésica*. Por eso la comuna **se propone y
se confirma**, exactamente como el aeródromo más cercano (`R10.1`), y no se
presenta como un hecho establecido.

Consecuencia concreta de la simplificación (Douglas-Peucker a ~111 m): un punto a
menos de ~111 m de un límite comunal puede resolver a la vecina. Se dice acá, se
dice en el archivo de datos y se dice en pantalla; callarlo sería justo el dato con
cara de autoritativo que `LV-93` dejó prohibido.

**Sin dependencias nuevas.** El shapefile de BCN se convirtió una vez a un archivo
de texto compacto (el guion vive en el historial de esta fila, no en el árbol), y
lo que queda acá es una prueba punto-en-polígono de veinte líneas. Traer GDAL o
shapely a este proyecto por esto sería pagar un compilador nativo por un algoritmo
que cabe en una pantalla.

**Regla par-impar sobre todos los anillos.** Un shapefile mezcla anillos externos
—islas de la misma comuna— con huecos, y no los distingue por orden. Contar en
cuántos cae el punto y mirar la paridad resuelve los dos casos de una vez: dentro
de una isla es 1 (impar, dentro), dentro de un hueco es 2 (par, fuera). Distinguir
externos de huecos por su orientación sería más código para el mismo resultado.
"""

import math
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "comunas.txt"


@lru_cache(maxsize=1)
def _comunas():
    """Las 346 comunas, leídas una vez por proceso.

    Son ~4 MB de texto y un cuarto de millón de vértices: la primera llamada
    después de un reinicio paga la lectura (del orden de un segundo) y las demás
    no pagan nada. Se prefiere eso a un índice en la base, que habría que migrar
    y mantener sincronizado con un archivo que cambia una vez cada varios años.
    """
    entries = []
    with DATA_FILE.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            code, comuna, provincia, region, bbox, rings = line.rstrip("\n").split(
                "|", 5
            )
            min_lat, min_lon, max_lat, max_lon = (float(v) for v in bbox.split(","))
            parsed_rings = []
            for ring in rings.split(";"):
                points = []
                for vertex in ring.split(" "):
                    lat, _, lon = vertex.partition(",")
                    points.append((float(lat), float(lon)))
                parsed_rings.append(points)
            entries.append(
                {
                    "code": code,
                    "comuna": comuna,
                    "provincia": provincia,
                    "region": region,
                    "bbox": (min_lat, min_lon, max_lat, max_lon),
                    "rings": parsed_rings,
                }
            )
    return entries


def _in_ring(lat, lon, ring):
    """Trazado de rayo: cuántas aristas cruza una semirrecta hacia el este."""
    inside = False
    previous_lat, previous_lon = ring[-1]
    for current_lat, current_lon in ring:
        if (current_lat > lat) != (previous_lat > lat):
            # Longitud del cruce a la altura de `lat`.
            crossing = previous_lon + (lat - previous_lat) * (
                current_lon - previous_lon
            ) / (current_lat - previous_lat)
            if lon < crossing:
                inside = not inside
        previous_lat, previous_lon = current_lat, current_lon
    return inside


def locate(latitude, longitude):
    """`{'comuna', 'provincia', 'region', 'code'}` del punto, o None.

    None cuando el punto cae fuera de Chile continental **o** en el territorio
    que la capa de BCN no cubre. Es una respuesta legítima y no un error: mejor
    no decir nada que nombrar una comuna equivocada.
    """
    if latitude is None or longitude is None:
        return None
    latitude, longitude = float(latitude), float(longitude)
    for entry in _comunas():
        min_lat, min_lon, max_lat, max_lon = entry["bbox"]
        # El recuadro descarta 345 de 346 sin mirar un solo vértice. Se guarda el
        # de la geometría **original** a propósito: uno calculado sobre la versión
        # simplificada podría excluir por unos metros un punto que sí está dentro.
        if not (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon):
            continue
        crossings = sum(
            1 for ring in entry["rings"] if _in_ring(latitude, longitude, ring)
        )
        if crossings % 2 == 1:
            return {
                "code": entry["code"],
                "comuna": entry["comuna"],
                "provincia": entry["provincia"],
                "region": entry["region"],
            }
    return None


# ---------------------------------------------------------------------------
# LV-366: buscador LOCAL de comunas (sin red) para el tiempo.
# ---------------------------------------------------------------------------

# La capa de BCN trae una «región» que no lo es (territorio sin demarcar): no se ofrece.
_NOT_A_PLACE_REGION = "Zona sin demarcar"
_PUNTA_ARENAS_ZONE_REGION = "Región de Magallanes y Antártica Chilena"
_EASTER_CODE = "5201"
SEARCH_LIMIT = 8
_SCAN_LINES = 9


def normalize_name(text):
    """Minúsculas sin tildes ni eñes (`Ñuñoa` -> `nunoa`), espacios colapsados."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def zone_for_comuna(entry):
    """Zona horaria de la comuna: Magallanes y Pascua tienen la suya; el resto, Santiago."""
    if entry["code"] == _EASTER_CODE:
        return "Pacific/Easter"
    if entry["region"] == _PUNTA_ARENAS_ZONE_REGION:
        return "America/Punta_Arenas"
    return "America/Santiago"


def _ring_area(ring):
    total = 0.0
    previous_lat, previous_lon = ring[-1]
    for lat, lon in ring:
        total += previous_lon * lat - lon * previous_lat
        previous_lat, previous_lon = lat, lon
    return abs(total) / 2


def _crossings(lat, rings):
    """Longitudes ordenadas donde la recta de latitud `lat` cruza algún anillo."""
    found = []
    for ring in rings:
        previous_lat, previous_lon = ring[-1]
        for current_lat, current_lon in ring:
            if (current_lat > lat) != (previous_lat > lat):
                found.append(
                    previous_lon
                    + (lat - previous_lat)
                    * (current_lon - previous_lon)
                    / (current_lat - previous_lat)
                )
            previous_lat, previous_lon = current_lat, current_lon
    return sorted(found)


def interior_point(entry):
    """`(lat, lon)` DENTRO del polígono de la comuna (no el centro de su recuadro).

    El centro del recuadro cae fuera en comunas largas, curvas o con islas (Cabo de Hornos, las
    del litoral). Se recorren varias latitudes del anillo principal, se toman los tramos de
    adentro (regla par-impar sobre TODOS los anillos, como `locate`) y se elige el punto medio del
    tramo más ancho. Es referencial: BCN simplifica sus límites a ~111 m.
    """
    best = None  # (ancho aproximado, lat, lon)
    main = max(entry["rings"], key=_ring_area)
    lats = [lat for lat, _ in main]
    low, high = min(lats), max(lats)
    for step in range(1, _SCAN_LINES + 1):
        lat = low + (high - low) * step / (_SCAN_LINES + 1)
        crossings = _crossings(lat, entry["rings"])
        for start, end in zip(crossings[0::2], crossings[1::2], strict=False):
            width = (end - start) * math.cos(math.radians(lat))
            if best is None or width > best[0]:
                best = (width, lat, (start + end) / 2)
    if best is None:
        min_lat, min_lon, max_lat, max_lon = entry["bbox"]
        return (min_lat + max_lat) / 2, (min_lon + max_lon) / 2
    return round(best[1], 4), round(best[2], 4)


def search_comunas(query, limit=SEARCH_LIMIT):
    """Comunas cuyo nombre coincide con `query` (sin tildes ni mayúsculas), mejores primero.

    Orden: nombre exacto, empieza con el texto, una palabra empieza con el texto, lo contiene; a
    igual categoría, por nombre (estable: el formulario repite la búsqueda y elige por posición).
    Cada resultado lleva comuna, provincia, región, un punto interior y la zona horaria.
    """
    needle = normalize_name(query)
    if not needle:
        return []
    ranked = []
    for entry in _comunas():
        if entry["region"] == _NOT_A_PLACE_REGION:
            continue
        name = normalize_name(entry["comuna"])
        if name == needle:
            rank = 0
        elif name.startswith(needle):
            rank = 1
        elif any(word.startswith(needle) for word in name.split()):
            rank = 2
        elif needle in name:
            rank = 3
        else:
            continue
        ranked.append((rank, name, entry))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]["code"]))
    results = []
    for _rank, _name, entry in ranked[:limit]:
        lat, lon = interior_point(entry)
        results.append(
            {
                "code": entry["code"],
                "comuna": entry["comuna"],
                "provincia": entry["provincia"],
                "region": entry["region"],
                "latitude": lat,
                "longitude": lon,
                "timezone": zone_for_comuna(entry),
            }
        )
    return results
