"""R9.1: separar un KMZ multi-círculo en las secciones que SIGO exige.

El formulario de solicitud de vuelo de SIGO acepta **una circunferencia con su
punto central por solicitud**, y el trabajo real llega al revés: el KMZ de MLP
trae 47 pares punto+círculo en carpetas separadas (`Puntos` / `Radios de 30 m`).
Preparar las solicitudes a mano significa aislar círculo por círculo en Google
Earth, pasar el centro a grados/minutos/segundos y estimar la distancia al
aeródromo — trabajo de transcripción que este módulo elimina.

Funciones puras sobre el documento canónico ("AeroKML JSON"): sin modelos, sin
vistas, sin IO. Quien persiste secciones (R9.3) y quien las muestra (la hoja
SIGO) llaman acá; los tests corren contra la estructura del KMZ real.

Decisiones:

- **El emparejamiento es por cercanía, no por nombre.** En el KMZ real el punto
  se llama "Quebrada km 13.760" y su círculo vive en otra carpeta; confiar en
  el nombre funcionaría hoy y se rompería con el primer KMZ dibujado distinto.
  Cada polígono se asigna al punto más cercano a su centroide, con umbral
  proporcional a su propio radio.
- **Lo desemparejado no se descarta ni se inventa**: un punto sin círculo o un
  círculo sin punto sale como sección con aviso (`WARNING_*`). Un KMZ a medias
  debe verse a medias — SIGO va a rechazar la solicitud igual, y acá es donde
  se puede corregir.
- **Los avisos son códigos, no frases**: la pantalla los redacta y traduce. Un
  test que afirme la frase literal se rompe con el idioma, que es la fragilidad
  que este repo ya pagó (`LV-95`).
"""

import math
from dataclasses import dataclass, field

from .kml.canonical import empty_document, iter_placemarks, new_uid

# Radio medio terrestre (IUGG). Para distancias al aeródromo (decenas a cientos
# de km) el error del modelo esférico queda muy por debajo de lo que la casilla
# "Distancia al AMC (Kilómetros)" puede expresar; un elipsoide sería una
# dependencia nueva para ganar decimales que el formulario no pide.
EARTH_RADIUS_KM = 6371.0088

# El polígono se acepta como circunferencia si sus vértices no se apartan del
# radio medio más que esto. Un rectángulo o un polígono a mano alzada supera el
# umbral por lejos; el círculo de 36 lados que dibujan las herramientas queda
# muy por debajo.
MAX_RADIUS_DEVIATION = 0.10

# Códigos de aviso. La pantalla decide la frase; los tests afirman el código.
WARNING_NO_CIRCLE = "no_circle"
WARNING_NO_CENTER_POINT = "no_center_point"
WARNING_NOT_A_CIRCLE = "not_a_circle"
# Otro punto del mismo documento comparte estas coordenadas. Encontrado en el
# KMZ real de MLP al primer uso: "Quebrada km 46.272" y "Quebrada km 46.924"
# —quebradas distintas, a 650 m una de otra según sus nombres— apuntan al mismo
# lugar, señal de una fila mal transcrita en la tabla de origen. Una solicitud
# SIGO con ese centro se presentaría por el sitio equivocado; callarlo sería
# dejar que el error viaje al formulario del Estado con timbre y todo.
WARNING_DUPLICATE_CENTER = "duplicate_center"


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia esférica en kilómetros. Argumentos sueltos a propósito:
    el canónico guarda [lon, lat] y una tupla ambigua es exactamente el tipo
    de error silencioso que no se nota hasta que el AMC sale al otro lado."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def to_dms(value, axis):
    """Las casillas de SIGO tal cual: grados, minutos, segundos y hemisferio.

    El formulario pide seis casillas numéricas sin signo (Grados/Minutos/
    Segundos por eje); el hemisferio se devuelve como letra aparte. Los
    segundos van con dos decimales y el acarreo se normaliza: 59.999" es
    0" del minuto siguiente, nunca "60.0"", que es un valor que ninguna
    casilla acepta.
    """
    if axis not in ("lat", "lon"):
        raise ValueError(f"axis must be 'lat' or 'lon', got {axis!r}")
    if axis == "lat":
        hemisphere = "S" if value < 0 else "N"
    else:
        hemisphere = "W" if value < 0 else "E"
    magnitude = abs(value)
    degrees = int(magnitude)
    remainder = (magnitude - degrees) * 60
    minutes = int(remainder)
    seconds = round((remainder - minutes) * 60, 2)
    if seconds >= 60:
        seconds = round(seconds - 60, 2)
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return {
        "degrees": degrees,
        "minutes": minutes,
        "seconds": seconds,
        "hemisphere": hemisphere,
    }


def format_dms(value, axis):
    """`31° 53' 39.81" S` — para la hoja SIGO y los listados."""
    dms = to_dms(value, axis)
    return (
        f"{dms['degrees']}° {dms['minutes']}' "
        f'{dms["seconds"]:.2f}" {dms["hemisphere"]}'
    )


@dataclass
class Section:
    """Una solicitud SIGO en potencia: un punto central y su circunferencia.

    `center` es (lat, lon) — orden geográfico, no el [lon, lat] del canónico,
    porque de acá en adelante los consumidores son humanos y formularios.
    `radius_m` es None cuando no hay círculo del cual estimarlo.
    """

    name: str
    center: tuple
    radius_m: float | None = None
    radius_deviation: float | None = None
    point: dict | None = None
    circle: dict | None = None
    warnings: list = field(default_factory=list)


def _ring_vertices(ring):
    """Vértices únicos del anillo: el KML repite el primero al final."""
    if len(ring) > 1 and ring[0][:2] == ring[-1][:2]:
        return ring[:-1]
    return ring


def _centroid(ring):
    """Media simple de los vértices, en (lat, lon).

    Para una circunferencia los vértices equidistan del centro, así que la
    media ES el centro; no hace falta el centroide de área, que pesa distinto
    los polígonos irregulares que este módulo de todos modos marca con aviso.
    """
    vertices = _ring_vertices(ring)
    lat = sum(v[1] for v in vertices) / len(vertices)
    lon = sum(v[0] for v in vertices) / len(vertices)
    return (lat, lon)


def estimate_radius_m(center, ring):
    """(radio medio en metros, desviación relativa) del anillo contra `center`.

    Se miden los vértices **y el punto medio de cada arista**, y la desviación
    es (máx − mín) / media. Los vértices solos no bastan, y el contraejemplo es
    exacto: **las cuatro esquinas de un rectángulo equidistan de su centro**,
    así que un rectángulo pasaría por círculo perfecto — encontrado por el
    propio test antes de escribir esta línea. El punto medio de la arista lo
    delata (en el lado largo queda mucho más cerca del centro), mientras que en
    un círculo real de 36 lados apenas se aparta un 0.4% del radio. Quien llama
    decide el umbral (`MAX_RADIUS_DEVIATION`); esta función sólo mide.
    """
    lat, lon = center
    vertices = _ring_vertices(ring)
    samples = []
    for index, vertex in enumerate(vertices):
        samples.append(vertex)
        following = vertices[(index + 1) % len(vertices)]
        # Punto medio en el plano lat/lon: a la escala de una solicitud SIGO
        # (decenas o cientos de metros) coincide con el geodésico.
        samples.append(
            [
                (vertex[0] + following[0]) / 2,
                (vertex[1] + following[1]) / 2,
            ]
        )
    distances = [haversine_km(lat, lon, s[1], s[0]) * 1000 for s in samples]
    mean = sum(distances) / len(distances)
    if mean == 0:
        return 0.0, 0.0
    deviation = (max(distances) - min(distances)) / mean
    return mean, deviation


def split_sections(document):
    """Separar un documento canónico en secciones punto+circunferencia.

    Devuelve una lista de `Section` en el orden de los puntos en el documento
    (que es el orden en que la persona los dibujó y espera verlos). Los
    polígonos huérfanos van al final, cada uno como sección con aviso.
    """
    points = []
    polygons = []
    for placemark in iter_placemarks(document):
        geometry = placemark.get("geometry") or {}
        if geometry.get("type") == "Point" and geometry.get("coordinates"):
            points.append(placemark)
        elif geometry.get("type") == "Polygon" and geometry.get("coordinates"):
            polygons.append(placemark)

    # Todos los pares (polígono, punto) dentro del umbral, no sólo el punto más
    # cercano de cada polígono. La versión "sólo el más cercano" falló al
    # primer uso contra el KMZ real: MLP trae puntos **coincidentes** (dos
    # registros de la misma quebrada, o un dato mal transcrito) con sus dos
    # círculos encima — ambos círculos elegían el mismo punto, uno perdía el
    # reclamo y quedaba huérfano con su punto gemelo al lado. Con todos los
    # pares en la mesa, el reclamo voraz por distancia deja a cada uno con el
    # suyo, y el duplicado se delata aparte (`WARNING_DUPLICATE_CENTER`) en vez
    # de disfrazarse de desemparejado.
    candidates = []  # (distance_m, polygon_index, point_index)
    measured = []  # (centroid, radius_m, deviation) por polígono
    for poly_index, polygon in enumerate(polygons):
        ring = polygon["geometry"]["coordinates"][0]
        centroid = _centroid(ring)
        radius_m, deviation = estimate_radius_m(centroid, ring)
        measured.append((centroid, radius_m, deviation))
        threshold = max(3 * radius_m, 100.0)
        for point_index, point in enumerate(points):
            coords = point["geometry"]["coordinates"]
            distance_m = (
                haversine_km(centroid[0], centroid[1], coords[1], coords[0]) * 1000
            )
            if distance_m <= threshold:
                candidates.append((distance_m, poly_index, point_index))

    claimed_by_point = {}
    claimed_polygons = set()
    for _distance_m, poly_index, point_index in sorted(candidates):
        if point_index not in claimed_by_point and poly_index not in claimed_polygons:
            claimed_by_point[point_index] = poly_index
            claimed_polygons.add(poly_index)

    sections = []
    for point_index, point in enumerate(points):
        coords = point["geometry"]["coordinates"]
        section = Section(
            name=point.get("name") or f"Punto {point_index + 1}",
            center=(coords[1], coords[0]),
            point=point,
        )
        poly_index = claimed_by_point.get(point_index)
        if poly_index is None:
            section.warnings.append(WARNING_NO_CIRCLE)
        else:
            polygon = polygons[poly_index]
            # El radio se mide desde el punto declarado, no desde el centroide:
            # el punto es lo que la persona afirmó como centro y lo que SIGO
            # recibirá como tal.
            ring = polygon["geometry"]["coordinates"][0]
            radius_m, deviation = estimate_radius_m(section.center, ring)
            section.circle = polygon
            section.radius_m = radius_m
            section.radius_deviation = deviation
            if deviation > MAX_RADIUS_DEVIATION:
                section.warnings.append(WARNING_NOT_A_CIRCLE)
        sections.append(section)

    matched = set(claimed_by_point.values())
    for poly_index, polygon in enumerate(polygons):
        if poly_index in matched:
            continue
        centroid, radius_m, deviation = measured[poly_index]
        orphan = Section(
            name=polygon.get("name") or f"Circunferencia {poly_index + 1}",
            center=centroid,
            radius_m=radius_m,
            radius_deviation=deviation,
            circle=polygon,
            warnings=[WARNING_NO_CENTER_POINT],
        )
        if deviation > MAX_RADIUS_DEVIATION:
            orphan.warnings.append(WARNING_NOT_A_CIRCLE)
        sections.append(orphan)

    # Dos secciones sobre las mismas coordenadas (redondeadas al sexto decimal,
    # ~10 cm): o un registro duplicado o una fila mal transcrita en la tabla de
    # origen. Se marcan **todas** las del grupo, porque el motor no puede saber
    # cuál dice la verdad — eso lo arbitra la persona con la tabla al frente, y
    # para eso necesita ver el grupo completo. Corre al final, con los
    # huérfanos ya dentro, para que un círculo sin punto coincidente con otra
    # sección no se escape del grupo.
    centers = {}
    for section in sections:
        key = (round(section.center[0], 6), round(section.center[1], 6))
        centers.setdefault(key, []).append(section)
    for group in centers.values():
        if len(group) > 1:
            for section in group:
                section.warnings.append(WARNING_DUPLICATE_CENTER)

    return sections


def nearest_aerodromes(center, aerodromes, limit=3):
    """R9.2: los aeródromos más cercanos al centro, con su distancia en km.

    Devuelve `[(aerodrome, distance_km), ...]` ordenado de más cerca a más
    lejos. **Ignora los que no tienen coordenadas** — no los adivina ni los
    pone al final: un aeródromo sin posición no puede ser "el más cercano", y
    quien llama debe contar cuántos quedaron fuera para poder decirlo en
    pantalla (`Aerodrome.is_locatable`).

    Devuelve varios y no sólo el primero a propósito: la casilla de SIGO es una
    sola, pero la persona confirma contra la carta AIP, y un segundo candidato
    a distancia parecida es justo lo que necesita ver para dudar. Con `limit=1`
    la pantalla mostraría una respuesta sin margen.
    """
    lat, lon = center
    ranked = [
        (
            aerodrome,
            haversine_km(
                lat, lon, float(aerodrome.latitude), float(aerodrome.longitude)
            ),
        )
        for aerodrome in aerodromes
        if aerodrome.latitude is not None and aerodrome.longitude is not None
    ]
    ranked.sort(key=lambda pair: pair[1])
    return ranked[:limit]


def _bare_placemark(source, *, geometry):
    """Copia mínima de un placemark: nombre y geometría, nada más.

    Sin estilos, `extras` ni `ExtendedData`: son fragmentos XML crudos del
    documento madre que la sección no necesita — y re-emitir XML ajeno en un
    archivo que se va a subir a un sistema del Estado es superficie de sorpresa
    que no compra nada.
    """
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": source.get("name", "") if source else "",
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": geometry,
        "extended_data": None,
        "extras": [],
    }


def build_section_document(section):
    """Documento canónico mínimo de una sección: su punto y su circunferencia.

    Es lo que `build_kml_bytes` convierte en el KMZ individual que SIGO exige
    ("una circunferencia con su punto central"). Una sección sin círculo o sin
    punto igual se construye con lo que tiene: el archivo incompleto en manos
    de la persona vale más que un error acá.
    """
    document = empty_document()
    document["name"] = section.name
    if section.point is not None:
        document["children"].append(
            _bare_placemark(section.point, geometry=dict(section.point["geometry"]))
        )
    if section.circle is not None:
        circle = _bare_placemark(
            section.circle, geometry=dict(section.circle["geometry"])
        )
        if not circle["name"]:
            circle["name"] = section.name
        document["children"].append(circle)
    return document
