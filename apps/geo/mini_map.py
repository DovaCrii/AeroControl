"""LV-368 (fase 4): los datos del mini-mapa de un plan, listos para `json_script`.

El mini-mapa es de **sólo lectura**: dibuja lo que el KMZ trae (centro, círculo o
vértices del área, y el aeródromo más cercano) para que quien llena un permiso
confirme de un vistazo que el plan es el que cree. No edita nada y no tiene
herramientas de dibujo.

Lo que viaja al navegador es el GeoJSON de **la misma sección** que arma
`build_section_document` (la que SIGO recibe como KMZ individual), más lo que la
fila de `plan_sections` ya calculó. Nada se vuelve a derivar acá: una segunda
cuenta del centro o del radio es cómo el mapa y la hoja acaban diciendo cosas
distintas (`LV-132`).
"""

from django.conf import settings
from django.utils.translation import gettext

from .kml.canonical import iter_placemarks
from .sections import build_section_document

# Seis decimales son ~11 cm: de sobra para ver un área de vuelo, y no regalan la
# precisión de origen de un archivo que es del cliente.
PRECISION = 6

TILE_KEYS = ("id", "name", "url", "attribution", "maxZoom", "default")


def _rounded(value):
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    if isinstance(value, float):
        return round(value, PRECISION)
    return value


def _geometries(section):
    """Las geometrías GeoJSON que dibuja la sección: punto y círculo, línea o polígono."""
    found = []
    for placemark in iter_placemarks(build_section_document(section)):
        geometry = placemark.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if geometry.get("type") and coordinates:
            found.append(
                {"type": geometry["type"], "coordinates": _rounded(coordinates)}
            )
    return found


def _aerodrome(row):
    amc = row.get("amc")
    if amc is None or amc.latitude is None or amc.longitude is None:
        return None
    return {
        "code": amc.code,
        "name": amc.name,
        "lat": round(float(amc.latitude), PRECISION),
        "lon": round(float(amc.longitude), PRECISION),
        "distance_km": row.get("amc_distance_km"),
    }


def tile_providers():
    """Las teselas ya configuradas (`GEO_TILE_PROVIDERS`): ningún proveedor nuevo."""
    return [
        {key: provider[key] for key in TILE_KEYS if key in provider}
        for provider in settings.GEO_TILE_PROVIDERS
    ]


def mini_map_payload(rows):
    """El objeto que `mini-map.js` lee. `rows` son las filas de `plan_sections`."""
    areas = []
    for row in rows:
        areas.append(
            {
                "name": row["name"],
                "modality": row["modality"],
                # (lat, lon), el orden de Leaflet; el centro que se declara, que
                # sobre un área irregular es el del círculo que la encierra.
                "center": [round(row["lat"], PRECISION), round(row["lon"], PRECISION)],
                "radius_m": row["radius_m"],
                "enclosing": bool(row["is_enclosing"]),
                "geometries": _geometries(row["section"]),
                "amc": _aerodrome(row),
            }
        )
    return {
        "tiles": tile_providers(),
        "areas": areas,
        "i18n": {
            "center": gettext("Centre point"),
            "radius": gettext("Radius (m)"),
            "amc": gettext("Nearest aerodrome (AMC)"),
            "km": gettext("km"),
        },
    }
