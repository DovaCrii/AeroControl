"""R10.8: la circunferencia **mínima** que encierra un área irregular.

SIGO acepta *una circunferencia con su punto central* por solicitud, y el barrido
de los KMZ vigentes del 2026-08-24 mostró que la mayoría de las áreas reales no
son circunferencias: `CC 716`, `CC 861` (dos archivos), `PMCHS` y `Caren` son
polígonos a mano alzada, con radios equivalentes de 100 m a 12 km. La app
detectaba el problema (`not_a_circle`) y ahí terminaba: convertir ese polígono en
el centro y radio que hay que declarar se seguía haciendo a mano en Google Earth,
que es el trabajo de transcripción que `R9.1` existía para quitar.

**Mínima, y no "el centroide más la distancia al vértice más lejano".**
Esa versión es tres líneas y está mal por los dos lados: en un área alargada el
centroide no es el centro del círculo que la cubre, y el radio resultante puede
pasarse largo. Un radio de más **pide más espacio aéreo del necesario** —lo que
la DGAC evalúa y puede objetar—, y uno de menos deja parte de la faena fuera de
lo autorizado. La circunferencia mínima es única y no admite discusión: es el
único número que no hay que justificar.

Tampoco se usa una aproximación tipo Ritter (bola envolvente por dos pasadas),
que es más simple y entrega entre 5% y 20% de radio extra. Sobre un área de 12 km
eso es más de un kilómetro de radio regalado.

El algoritmo es el de **Welzl** en su forma incremental: se recorren los puntos y
cada vez que uno cae fuera del círculo vigente se reconstruye con ese punto en el
borde. Exacto y lineal en el caso esperado, que sobre los 770 vértices del anillo
más grande de la muestra es instantáneo.

**El plano local.** Se proyecta a metros contra un origen en el propio área
(equirrectangular escalada por el coseno de la latitud) antes de medir. A la
escala de una solicitud —decenas de metros a decenas de kilómetros— la diferencia
con el geodésico queda por debajo de la precisión que la casilla de SIGO admite,
y es la misma aproximación que `estimate_radius_m` ya hace para los puntos medios
de arista. Sobre miles de kilómetros no serviría, pero un permiso de vuelo de RPA
no cubre miles de kilómetros.
"""

import math
from random import Random

# Grados a metros sobre un meridiano. El mismo factor que usa el resto del
# módulo geométrico, para que dos partes del cálculo no discrepen en el tercer
# decimal por usar radios terrestres distintos.
METERS_PER_DEGREE = 111_320.0

# Welzl aleatoriza el orden de los puntos para su garantía de tiempo lineal. El
# **resultado** es único —la circunferencia mínima de un conjunto lo es—, pero se
# usa una semilla fija de todos modos: un número que se le muestra a una persona
# y que puede terminar copiado en un formulario del Estado no debería moverse en
# el último decimal entre dos visitas a la misma pantalla.
_RNG = Random(20260824)

# Tolerancia multiplicativa al preguntar "¿este punto está dentro?". Sin ella, el
# punto que define el borde puede quedar fuera de su propio círculo por error de
# redondeo y el algoritmo no converge.
_EPSILON = 1 + 1e-14


def _project(points, origin_lat, origin_lon):
    """(lon, lat) -> (x, y) en metros sobre un plano local."""
    cos_lat = math.cos(math.radians(origin_lat))
    return [
        (
            (point[0] - origin_lon) * METERS_PER_DEGREE * cos_lat,
            (point[1] - origin_lat) * METERS_PER_DEGREE,
        )
        for point in points
    ]


def _unproject(x, y, origin_lat, origin_lon):
    cos_lat = math.cos(math.radians(origin_lat))
    return (
        origin_lat + y / METERS_PER_DEGREE,
        origin_lon + x / (METERS_PER_DEGREE * cos_lat),
    )


def _distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _contains(circle, point):
    return (
        circle is not None
        and _distance(circle[0], circle[1], point[0], point[1]) <= circle[2] * _EPSILON
    )


def _from_two(a, b):
    center_x, center_y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return (center_x, center_y, _distance(center_x, center_y, a[0], a[1]))


def _cross(ox, oy, ax, ay, bx, by):
    return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)


def _circumcircle(a, b, c):
    """La circunferencia que pasa por tres puntos, o None si son colineales."""
    # Origen en el centroide del triángulo: acerca las magnitudes a cero antes de
    # elevarlas al cuadrado, que es donde un triángulo lejano pierde precisión.
    ox, oy = (
        (min(a[0], b[0], c[0]) + max(a[0], b[0], c[0])) / 2,
        (min(a[1], b[1], c[1]) + max(a[1], b[1], c[1])) / 2,
    )
    ax, ay = a[0] - ox, a[1] - oy
    bx, by = b[0] - ox, b[1] - oy
    cx, cy = c[0] - ox, c[1] - oy
    determinant = (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by)) * 2
    if determinant == 0:
        return None
    x = (
        (ax**2 + ay**2) * (by - cy)
        + (bx**2 + by**2) * (cy - ay)
        + (cx**2 + cy**2) * (ay - by)
    ) / determinant
    y = (
        (ax**2 + ay**2) * (cx - bx)
        + (bx**2 + by**2) * (ax - cx)
        + (cx**2 + cy**2) * (bx - ax)
    ) / determinant
    center_x, center_y = ox + x, oy + y
    radius = max(
        _distance(center_x, center_y, point[0], point[1]) for point in (a, b, c)
    )
    return (center_x, center_y, radius)


def _with_two_on_boundary(points, first, second):
    circle = _from_two(first, second)
    left = right = None
    for point in points:
        if _contains(circle, point):
            continue
        candidate = _circumcircle(first, second, point)
        if candidate is None:
            continue
        # De qué lado de la recta `first`-`second` cae: el círculo mínimo tiene
        # su centro del lado del punto que sobresale, y hay que quedarse con el
        # más extremo de cada lado antes de comparar radios.
        side = _cross(first[0], first[1], second[0], second[1], point[0], point[1])
        candidate_side = _cross(
            first[0], first[1], second[0], second[1], candidate[0], candidate[1]
        )
        if side > 0 and (
            left is None
            or candidate_side
            > _cross(first[0], first[1], second[0], second[1], left[0], left[1])
        ):
            left = candidate
        elif side < 0 and (
            right is None
            or candidate_side
            < _cross(first[0], first[1], second[0], second[1], right[0], right[1])
        ):
            right = candidate
    if left is None:
        return right or circle
    if right is None:
        return left
    return left if left[2] <= right[2] else right


def _with_one_on_boundary(points, boundary):
    circle = (boundary[0], boundary[1], 0.0)
    for index, point in enumerate(points):
        if _contains(circle, point):
            continue
        if circle[2] == 0.0:
            circle = _from_two(boundary, point)
        else:
            circle = _with_two_on_boundary(points[: index + 1], boundary, point)
    return circle


def smallest_enclosing_circle(points):
    """(centro_x, centro_y, radio) mínimo sobre puntos planos `(x, y)`.

    Público para poder testear la geometría sin latitudes de por medio.
    """
    if not points:
        return None
    shuffled = list(points)
    _RNG.shuffle(shuffled)
    circle = None
    for index, point in enumerate(shuffled):
        if _contains(circle, point):
            continue
        circle = _with_one_on_boundary(shuffled[: index + 1], point)
    return circle


def enclosing_circle_of_ring(ring):
    """`(lat, lon, radio_m)` de la circunferencia mínima que encierra el anillo.

    `ring` viene del canónico: `[[lon, lat, alt], ...]`. Devuelve None si no hay
    con qué calcular.
    """
    if not ring:
        return None
    origin_lat = sum(vertex[1] for vertex in ring) / len(ring)
    origin_lon = sum(vertex[0] for vertex in ring) / len(ring)
    circle = smallest_enclosing_circle(_project(ring, origin_lat, origin_lon))
    if circle is None:
        return None
    latitude, longitude = _unproject(circle[0], circle[1], origin_lat, origin_lon)
    return (latitude, longitude, circle[2])
