"""R9.3/R9.4: convertir un KMZ multi-círculo en solicitudes, y armarlas para SIGO.

Dos operaciones, las dos fuera de las vistas para que se puedan probar sin
cliente HTTP y reusar desde un comando si algún día hace falta:

- `create_requests_from_plan()` — separa el plan en secciones y crea una
  solicitud por cada una.
- `sigo_sheet()` — lo que la persona copia casilla por casilla en el
  formulario del Estado.

El motor geométrico vive en `apps.geo.sections` y no se duplica acá: esta capa
sólo decide qué se persiste y cómo se presenta.
"""

from decimal import Decimal

from django.db import transaction

from apps.geo.kml.build import build_kml_bytes
from apps.geo.kml.kmz import build_kmz
from apps.geo.sections import (
    build_section_document,
    format_dms,
    nearest_aerodromes,
    split_sections,
    to_dms,
)
from apps.registry.models import Aerodrome

from .models import FlightRequest


def _locatable_aerodromes():
    return list(
        Aerodrome.objects.filter(
            is_active=True, latitude__isnull=False, longitude__isnull=False
        )
    )


def plan_sections(plan):
    """R10.1: lo que el KMZ de un plan dice, **sin separarlo ni crear nada**.

    Corrige una premisa equivocada de R9: la única puerta para que un KMZ
    entregara su información (centro, radio, aeródromo más cercano y distancia)
    era **separarlo** en solicitudes. Eso convertía el caso excepcional —un
    archivo con cuarenta y siete circunferencias, como el de MLP— en el camino
    obligatorio del caso normal, que es **una sola circunferencia**: quien subía
    un KMZ corriente tenía que "separar" algo que no estaba junto.

    Ahora los datos se leen en la etapa del KMZ, que es donde el usuario los
    pidió. Devuelve una lista de dicts listos para pintar, uno por
    circunferencia — casi siempre uno.

    Es de sólo lectura y no toca la base: se puede llamar al dibujar una ficha
    sin efectos. Quien quiera persistir usa `create_requests_from_plan`, que
    reusa esta misma derivación.
    """
    if plan.current_version is None:
        return []
    aerodromes = _locatable_aerodromes()
    rows = []
    for section in split_sections(plan.current_version.content):
        nearest = nearest_aerodromes(section.center, aerodromes, limit=1)
        aerodrome, distance_km = nearest[0] if nearest else (None, None)
        lat, lon = section.center
        rows.append(
            {
                "section": section,
                "name": section.name,
                "lat": lat,
                "lon": lon,
                # Las seis casillas de SIGO, y la lectura corrida para cotejar
                # de un vistazo contra la carta.
                "dms_lat": to_dms(lat, "lat"),
                "dms_lon": to_dms(lon, "lon"),
                "lat_readable": format_dms(lat, "lat"),
                "lon_readable": format_dms(lon, "lon"),
                "radius_m": round(section.radius_m) if section.radius_m else None,
                "amc": aerodrome,
                "amc_distance_km": (
                    round(distance_km, 1) if distance_km is not None else None
                ),
                "warnings": list(section.warnings),
                "enclosing": _enclosing_row(section, aerodromes),
            }
        )
    return rows


def _enclosing_row(section, aerodromes):
    """R10.8: la circunferencia mínima que encierra un área que no es circular.

    **Con su propio AMC**, y esa es la parte que importa: lo que se declara en
    SIGO es este centro, no el punto original, así que la distancia al aeródromo
    tiene que medirse desde acá. Devolver el AMC del punto declarado junto a un
    centro distinto sería una fila internamente inconsistente — dos datos
    correctos por separado que juntos describen una solicitud que no existe.
    """
    if section.enclosing is None:
        return None
    latitude, longitude, radius_m = section.enclosing
    nearest = nearest_aerodromes((latitude, longitude), aerodromes, limit=1)
    aerodrome, distance_km = nearest[0] if nearest else (None, None)
    return {
        "lat": latitude,
        "lon": longitude,
        "dms_lat": to_dms(latitude, "lat"),
        "dms_lon": to_dms(longitude, "lon"),
        "lat_readable": format_dms(latitude, "lat"),
        "lon_readable": format_dms(longitude, "lon"),
        "radius_m": round(radius_m),
        "amc": aerodrome,
        "amc_distance_km": round(distance_km, 1) if distance_km is not None else None,
    }


@transaction.atomic
def create_requests_from_plan(plan, *, created_by, document=None):
    """Crear una `FlightRequest` por cada sección del plan.

    Devuelve `(solicitudes, secciones)` — las secciones también, porque traen
    los avisos que la pantalla debe mostrar y que no se guardan en el modelo:
    un aviso es un juicio sobre el archivo de origen, no un atributo de la
    solicitud, y persistirlo lo dejaría desactualizado en cuanto se corrija.

    `document` permite pasar un canónico ya parseado (el de la vista de vista
    previa) para no volver a leerlo; por defecto usa la versión vigente del
    plan.
    """
    if document is None:
        document = plan.current_version.content
    sections = split_sections(document)
    aerodromes = _locatable_aerodromes()

    requests = []
    for section in sections:
        lat, lon = section.center
        amc, distance_km = None, None
        ranked = nearest_aerodromes((lat, lon), aerodromes, limit=1)
        if ranked:
            amc, distance = ranked[0]
            distance_km = Decimal(f"{distance:.1f}")
        request = FlightRequest.objects.create(
            title=section.name,
            cost_center=plan.cost_center,
            source_plan=plan,
            # `round()` y no truncado: el radio se estima del polígono y SIGO
            # pide un entero en metros. None cuando no hay círculo -- la
            # sección con aviso se crea igual, porque esconderla obligaría a
            # volver al KMZ para descubrir que falta.
            radius_m=round(section.radius_m) if section.radius_m else None,
            center_lat=Decimal(f"{lat:.6f}"),
            center_lon=Decimal(f"{lon:.6f}"),
            amc=amc,
            amc_distance_km=distance_km,
            section_content=build_section_document(section),
        )
        requests.append(request)
    return requests, sections


def section_kmz(request):
    """Los bytes del KMZ que se adjunta a SIGO: una circunferencia y su punto.

    Se genera al vuelo desde `section_content` en vez de guardarse: cuarenta y
    siete solicitudes serían cuarenta y siete binarios que se pueden
    reconstruir exactamente, y el canónico ya está versionado por el plan madre.
    """
    return build_kmz(build_kml_bytes(request.section_content))


def sigo_sheet(request):
    """Los valores del formulario de SIGO, en el orden en que los pide.

    Cada entrada es `(etiqueta, valor)` con el valor ya en el formato de la
    casilla — las seis del punto centro por separado, porque SIGO las pide así
    y juntarlas obligaría a la persona a partirlas de nuevo a mano, que es
    justo el trabajo que esta pantalla existe para quitar.
    """
    lat, lon = float(request.center_lat), float(request.center_lon)
    dms_lat, dms_lon = to_dms(lat, "lat"), to_dms(lon, "lon")
    pairs = [
        (f"{item.work_area}", f"{item.objective}")
        for item in request.work_items.select_related("work_area", "objective")
    ]
    return {
        "request_type": request.get_request_type_display(),
        "work_pairs": pairs,
        "commune": request.commune,
        "area": request.area_name,
        "amc": str(request.amc) if request.amc else "",
        "amc_distance_km": request.amc_distance_km,
        # Las seis casillas, y además la lectura corrida para revisar de un
        # vistazo contra la carta.
        "lat_degrees": dms_lat["degrees"],
        "lat_minutes": dms_lat["minutes"],
        "lat_seconds": f"{dms_lat['seconds']:.2f}",
        "lat_hemisphere": dms_lat["hemisphere"],
        "lon_degrees": dms_lon["degrees"],
        "lon_minutes": dms_lon["minutes"],
        "lon_seconds": f"{dms_lon['seconds']:.2f}",
        "lon_hemisphere": dms_lon["hemisphere"],
        "lat_readable": format_dms(lat, "lat"),
        "lon_readable": format_dms(lon, "lon"),
        "radius_m": request.radius_m,
        "altitude_m": request.altitude_m,
        "hour_from": request.hour_from,
        "hour_to": request.hour_to,
    }


@transaction.atomic
def link_to_permission(request, permission, *, changed_by="", user=None):
    """Vincular la solicitud a su permiso y **rellenar** la ubicación de éste.

    Rellenar y no pisar: si el permiso ya trae una coordenada, la que manda es
    la suya — puede haberla tomado del papel DGAC, que es de más autoridad que
    lo que se preparó antes de presentar. Sólo se completan los huecos, y la
    solicitud avanza a "Vinculada al permiso".
    """
    request.flight_permission = permission
    request.status = FlightRequest.STATUS_LINKED
    request._changed_by = changed_by or "system"
    request._changed_by_user = user
    request.save(update_fields=["flight_permission", "status", "updated_at"])

    # R10.2: la aritmética vive en `FlightPermission.fill_location_gaps`, junto
    # al `clean()` que la restringe. Antes estaba acá, y era la única copia —
    # hasta que apareció la segunda fuente (vincular un plan directamente), que
    # es cuando este repo extrae.
    return permission.fill_location_gaps(
        latitude=request.center_lat,
        longitude=request.center_lon,
        radius_m=request.radius_m,
        commune=request.commune,
        area_name=request.area_name,
        altitude_m=request.altitude_m,
    )
