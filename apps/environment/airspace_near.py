"""El cruce «zonas de espacio aéreo cerca de las faenas con permiso vigente» (LV-358, E3).

UN solo cálculo, que usan la franja del panel y la «Situación del día» de la cabecera (no hay dos
sitios con la misma cifra). Es un HECHO, nunca un veredicto: cuántas zonas prohibidas, restringidas
o peligrosas de la foto vigente quedan a `AIRSPACE_NEAR_KM` o menos de una faena con permiso
vigente, con la fecha de la foto. No dice si se puede volar ni «activa» ninguna zona (LV-93).

Costo: tres consultas (la foto, las zonas y los permisos) sin importar cuántas faenas haya; la
distancia se calcula con las funciones puras de `apps/geo/airspace_geometry.py`, con el bbox de la
zona como prefiltro. Las faenas son las de los permisos aprobados y vigentes hoy, acotadas por
tenant, y se miden desde el punto del permiso (su círculo suma su radio) o, si el permiso no lo
trae, desde la coordenada de su centro de costo.
"""

from django.utils import timezone

from apps.airspace import payload
from apps.core.tenancy import scope_queryset_to_tenant
from apps.geo.airspace_geometry import bbox_near, distance_to_geometry_km
from apps.operations.models import FlightPermission

# Los tres tipos de zona de la sigla P/R/D. Las zonas navales y los aeródromos no cuentan acá.
ZONE_KINDS = ("prohibited", "restricted", "danger")
PERMISSIONS = ("airspace.view_airspacefeature", "operations.view_flightpermission")


def can_see(user):
    """La celda cruza dos fuentes: pide el permiso de cada una (LV-268)."""
    return getattr(user, "is_authenticated", False) and all(
        user.has_perm(perm) for perm in PERMISSIONS
    )


def current_permits(user, today=None):
    """Los permisos aprobados y vigentes hoy, acotados por tenant (la definición de «vigente» del repo).

    La usan la celda de la franja y la capa «Permisos vigentes» del mapa: una sola definición.
    """
    today = today or timezone.localdate()
    return scope_queryset_to_tenant(
        FlightPermission.objects.filter(
            is_active=True,
            status=FlightPermission.STATUS_APPROVED,
            valid_from__lte=today,
            valid_until__gte=today,
        ),
        user,
        "cost_center__tenant_id",
    )


def _sites(user, today):
    """`{(lat, lon, radio_km)}` de las faenas con permiso aprobado y vigente hoy (una consulta)."""
    permits = current_permits(user, today).values_list(
        "latitude",
        "longitude",
        "radius_km",
        "cost_center__latitude",
        "cost_center__longitude",
    )
    sites = set()
    for lat, lon, radius, cc_lat, cc_lon in permits:
        if lat is not None and lon is not None:
            sites.add((float(lat), float(lon), float(radius or 0)))
        elif cc_lat is not None and cc_lon is not None:
            sites.add((float(cc_lat), float(cc_lon), 0.0))
    return sites


def airspace_near_fact(user, near_km=None, today=None, now=None):
    """El hecho para `user`, o `None` si no puede verlo.

    `{"state": "nosnapshot"}` si nunca se importó una foto; si no,
    `{"state": "ok", count, sites, km, fetched_at, age_days, stale}`.
    """
    if not can_see(user):
        return None
    snapshot = payload.current_snapshot()
    if snapshot is None:
        return {"state": "nosnapshot"}
    near_km = payload.near_km() if near_km is None else near_km
    today = today or timezone.localdate()
    info = payload.snapshot_payload(snapshot, now)
    sites = _sites(user, today)
    count = 0
    if sites:
        zones = payload.active_features().filter(kind__in=ZONE_KINDS)
        for min_lon, min_lat, max_lon, max_lat, geometry in zones.values_list(
            "min_lon", "min_lat", "max_lon", "max_lat", "geometry"
        ):
            bbox = (min_lon, min_lat, max_lon, max_lat)
            for lat, lon, radius in sites:
                reach = near_km + radius
                if bbox_near(bbox, lat, lon, reach) and (
                    distance_to_geometry_km(lat, lon, geometry) <= reach
                ):
                    count += 1
                    break
    return {
        "state": "ok",
        "count": count,
        "sites": len(sites),
        "km": near_km,
        "fetched_at": snapshot.fetched_at,
        "age_days": info["age_days"],
        "stale": info["stale"],
    }
