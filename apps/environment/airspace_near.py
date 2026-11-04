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

from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from apps.airspace import payload
from apps.airspace.models import AirspaceFeature
from apps.core.tenancy import scope_queryset_to_tenant
from apps.geo.airspace_geometry import bbox_near, distance_to_geometry_km
from apps.operations.models import FlightPermission

# Los tres tipos de zona de la sigla P/R/D. Las zonas navales y los aeródromos no cuentan acá.
ZONE_KINDS = ("prohibited", "restricted", "danger")
PERMISSIONS = ("airspace.view_airspacefeature", "operations.view_flightpermission")
KIND_LABELS = dict(AirspaceFeature.KIND_CHOICES)


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


def pending_permits(user):
    """Los permisos aún «Solicitados» a la DGAC, activos y acotados por tenant (capa «en trámite», LV-379).

    Sin filtro de ubicación: quien dibuja decide qué hacer con los que no tienen coordenadas.
    """
    return scope_queryset_to_tenant(
        FlightPermission.objects.filter(
            is_active=True, status=FlightPermission.STATUS_REQUESTED
        ),
        user,
        "cost_center__tenant_id",
    )


def _sites(user, today):
    """`{(lat, lon, radio_km): permiso}` de las faenas con permiso aprobado y vigente hoy (una consulta).

    Dos permisos con el mismo punto y radio son UNA faena (la cifra cuenta faenas, no papeles); el
    permiso que la nombra es el primero por número, para que la tarjeta diga siempre el mismo.
    """
    permits = (
        current_permits(user, today)
        .order_by("permission_number", "pk")
        .values_list(
            "pk",
            "permission_number",
            "cost_center__code",
            "latitude",
            "longitude",
            "radius_km",
            "cost_center__latitude",
            "cost_center__longitude",
        )
    )
    sites = {}
    for pk, number, site, lat, lon, radius, cc_lat, cc_lon in permits:
        if lat is not None and lon is not None:
            key = (float(lat), float(lon), float(radius or 0))
        elif cc_lat is not None and cc_lon is not None:
            key = (float(cc_lat), float(cc_lon), 0.0)
        else:
            continue
        sites.setdefault(key, {"id": pk, "number": number or "", "site": site})
    return sites


# Cuántos pares zona–permiso nombra la tarjeta (LV-411); el resto se resume en «y N más».
PAIRS_SHOWN = 3


def _pair(zone, permit, distance_km):
    """Un par zona–permiso con sus enlaces: la ficha del permiso y el mapa centrado en los dos."""
    zone_id, kind, code, name = zone
    map_url = (
        reverse("airspace-map")
        + "?"
        + urlencode(
            {"permit": str(permit["id"]), "layer": "permits", "zone": str(zone_id)}
        )
    )
    return {
        "zone_id": str(zone_id),
        "kind": kind,
        "kind_label": str(KIND_LABELS.get(kind, kind)),
        "code": code,
        "name": name,
        "distance_km": round(distance_km, 1),
        "permit_number": permit["number"],
        "permit_site": permit["site"],
        "permit_url": reverse("permission-detail", args=[permit["id"]]),
        "map_url": map_url,
    }


def airspace_near_fact(user, near_km=None, today=None, now=None):
    """El hecho para `user`, o `None` si no puede verlo.

    `{"state": "nosnapshot"}` si nunca se importó una foto; si no,
    `{"state": "ok", count, sites, km, fetched_at, age_days, stale, pairs, more}`.

    `pairs` (LV-411) son las `PAIRS_SHOWN` zonas más cercanas, cada una con la faena con permiso que
    tiene más cerca y la distancia desde el BORDE del círculo del permiso (0 si la zona lo toca);
    `more` es cuántas zonas cercanas quedan sin nombrar. Sale del MISMO recorrido que la cifra.
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
    near = []
    if sites:
        zones = payload.active_features().filter(kind__in=ZONE_KINDS)
        for (
            pk,
            kind,
            code,
            name,
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            geometry,
        ) in zones.values_list(
            "pk",
            "kind",
            "code",
            "name",
            "min_lon",
            "min_lat",
            "max_lon",
            "max_lat",
            "geometry",
        ):
            bbox = (min_lon, min_lat, max_lon, max_lat)
            best = None
            for (lat, lon, radius), permit in sites.items():
                reach = near_km + radius
                if not bbox_near(bbox, lat, lon, reach):
                    continue
                distance = distance_to_geometry_km(lat, lon, geometry)
                if distance <= reach:
                    edge = max(0.0, distance - radius)
                    if best is None or edge < best[0]:
                        best = (edge, permit)
            if best is not None:
                near.append(((pk, kind, code, name), best[1], best[0]))
    near.sort(key=lambda item: (item[2], item[0][2] or "~", item[0][3]))
    return {
        "state": "ok",
        "count": len(near),
        "pairs": [_pair(*item) for item in near[:PAIRS_SHOWN]],
        "more": max(0, len(near) - PAIRS_SHOWN),
        "sites": len(sites),
        "km": near_km,
        "fetched_at": snapshot.fetched_at,
        "age_days": info["age_days"],
        "stale": info["stale"],
    }
