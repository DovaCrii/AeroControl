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

    filled = []
    if permission.latitude is None and permission.longitude is None:
        permission.latitude = request.center_lat
        permission.longitude = request.center_lon
        filled += ["latitude", "longitude"]
    if permission.radius_km is None and request.radius_m:
        permission.radius_km = Decimal(request.radius_m) / Decimal(1000)
        filled.append("radius_km")
    if not permission.commune and request.commune:
        permission.commune = request.commune
        filled.append("commune")
    if not permission.area_name and request.area_name:
        permission.area_name = request.area_name
        filled.append("area_name")
    if permission.max_altitude_ft is None and request.altitude_m:
        # SIGO acepta metros o pies; el permiso guarda pies (OPS-4). 1 m =
        # 3.28084 ft, redondeado al pie: la casilla no admite decimales.
        permission.max_altitude_ft = round(request.altitude_m * 3.28084)
        filled.append("max_altitude_ft")
    if filled:
        permission.save(update_fields=filled + ["updated_at"])
    return filled
