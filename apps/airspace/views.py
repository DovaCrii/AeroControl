"""The «Airspace» tab of the Environment section (LV-357, phase 3) and its two data endpoints.

* `AirspaceTab`   GET /environment/airspace/            the screen (404 with an import guide if no snapshot)
* `AirspaceData`  GET /environment/airspace/data.json   the current snapshot as JSON (ETag = its sha256)
* `AirspaceNear`  GET /environment/airspace/near/       what contains / is near a point or circle
* `AirspaceOwnLayers` GET /environment/airspace/own-layers.json?layer=sites|permits  the person's own layers

The first three need `view_airspacefeature` (LV-268). The catalog is global (no tenant), like `Aerodrome`.
`near/` runs the very same pure functions as `apps/geo/airspace_geometry.py`, so the client never
re-implements the distance maths that decides "this zone touches your circle".

What this screen never says: "you can fly", a buffer or minimum distance nobody wrote, a vertical
limit converted to a number, or that a zone "is active now". The source's words travel as written.
"""

import math

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.core.views import ModelViewPermissionRequiredMixin
from apps.core.tenancy import scope_queryset_to_tenant
from apps.environment.airspace_near import current_permits
from apps.environment.views import EnvironmentTab, environment_context
from apps.geo import administrative_layer
from apps.geo.airspace_geometry import features_in_area, nearby
from apps.geo.sections import format_dms

from . import payload
from .models import AirspaceFeature

MAX_RADIUS_KM = 1000.0
NEAREST_AERODROMES = 3


def near_km():
    """«Near» in kilometres (the person's decision of 2026-10-20; `AIRSPACE_NEAR_KM`)."""
    return payload.near_km()


def kind_labels():
    return {key: str(label) for key, label in AirspaceFeature.KIND_CHOICES}


def ui_strings():
    """Every string the script draws, translated here so `makemessages` can see them."""
    return {
        "noResults": _("Nothing matches. Check the code or try part of the name."),
        "moreResults": _("{n} more. Refine the search to see them."),
        "resultsCount": _("{n} results"),
        "noCode": _("no code"),
        "unofficial": _("not official"),
        "km": _("km"),
        "nm": _("NM"),
        "heading": _("true heading"),
        "measureTotal": _("Total"),
        "measureLeg": _("Last leg"),
        "measureHint": _(
            "Click the map to add points. Double-click or press Escape to finish."
        ),
        "circleHint": _("Click the map to place the centre of the circle."),
        "nearHint": _("Click the map to ask what is around that point."),
        "invalidCoordinate": _("That coordinate is not valid: {reason}."),
        "reasonLat": _("latitude outside -90 to 90"),
        "reasonLon": _("longitude outside -180 to 180"),
        "reasonMinutes": _("minutes and seconds must be below 60"),
        "reasonSign": _("use a sign or a hemisphere letter, not both"),
        "reasonAxis": _("one latitude and one longitude are needed"),
        "loading": _("Loading the map data"),
        "loadFailed": _("The map data could not be loaded."),
        "nearFailed": _("The query failed. Try again."),
        "inside": _("Inside"),
        "touching": _("Touches the circle"),
        "nearby": _("Near"),
        "nearestAerodromes": _("Nearest aerodromes"),
        "none": _("None"),
        "layerShown": _("{name}: shown"),
        "layerHidden": _("{name}: hidden"),
        "selected": _("Selected: {name}"),
        "toCentre": _("to the centre"),
        "notStated": _("Not stated in the source"),
        "referenceFrom": _("Distances are measured from {label}."),
        "layerOwnHeading": _("My layers (off by default)"),
        "layerSites": _("My sites"),
        "layerPermits": _("Current permits"),
        "layerOwnFailed": _("Your layer could not be loaded. Try again."),
        "layerOwnEmpty": _("Nothing to show on this layer."),
        "siteWord": _("Site"),
        "permitWord": _("Permit"),
        "validUntil": _("valid until {date}"),
        "layerAdmin": _("Administrative boundaries"),
        "adminLoading": _("Loading the administrative boundaries"),
        "adminFailed": _(
            "The administrative boundaries could not be loaded. Try again."
        ),
        "adminInside": _("Inside {name}"),
        "adminCommunes": _("{n} communes"),
        "adminContained": _("Zones inside"),
        "adminTouching": _("Zones that touch it"),
        "adminAerodromes": _("Aerodromes inside"),
        "adminReferential": _("Referential, BCN source, within about 111 m."),
        "adminSummary": _("{zones} zones and {aerodromes} aerodromes in {name}"),
    }


def admin_kind_labels():
    """The labels of the administrative search types (communes, regions and the BCN undemarcated zone)."""
    return {
        "commune": _("Commune"),
        "region": _("Region"),
        "undemarcated": _("Undemarcated zone"),
    }


# The person's own layers (LV-358, E3): each one needs ITS model's view permission, on top of the
# map's, and is cut by the user's tenant. Off by default in the map; fetched only when switched on.
OWN_LAYERS = {
    "sites": "registry.view_costcenter",
    "permits": "operations.view_flightpermission",
}


def own_layers_for(user):
    """The own layers `user` may load: `[{key, url}]`, in order. Empty when they have none."""
    return [
        {"key": key, "url": f"{reverse('airspace-own-layers')}?layer={key}"}
        for key, permission in OWN_LAYERS.items()
        if user.has_perm(permission)
    ]


def tab_config(reference, own_layers=()):
    kinds = kind_labels()
    kinds.update({key: str(label) for key, label in admin_kind_labels().items()})
    return {
        "ownLayers": list(own_layers),
        "dataUrl": reverse("airspace-data"),
        "nearUrl": reverse("airspace-near"),
        # The administrative layer (LV-367): it is fetched only when the person switches it on.
        # `{code}` is replaced by the script. The search index travels here (names and frames, no
        # geometry) so communes and regions can be searched with the layer off.
        "adminUrl": reverse("airspace-admin"),
        "adminContainsUrl": reverse("airspace-admin-contains", args=["__code__"]),
        "adminIndex": administrative_layer.search_index(),
        "nearKm": near_km(),
        "tileProviders": settings.GEO_TILE_PROVIDERS,
        "reference": reference,
        "kinds": kinds,
        "i18n": ui_strings(),
    }


class AirspaceTab(EnvironmentTab):
    """The screen. Without a snapshot it answers 404 and explains how to import one."""

    model = AirspaceFeature
    tab_key = "airspace"
    template_name = "environment/airspace_tab.html"

    def get(self, request):
        context = environment_context(request.user)
        context["env_active"] = self.tab_key
        snapshot = payload.current_snapshot()
        context["snapshot"] = snapshot
        if snapshot is None:
            return render(request, self.template_name, context, status=404)
        data = payload.snapshot_payload(snapshot)
        counts = {kind: 0 for kind in payload.SHOWN_KINDS}
        for kind in payload.active_features().values_list("kind", flat=True):
            counts[kind] = counts.get(kind, 0) + 1
        labels = kind_labels()
        location = context.get("env_location")
        reference = (
            {
                "lat": float(location.latitude),
                "lon": float(location.longitude),
                "label": location.label,
            }
            if location is not None
            else None
        )
        context.update(
            {
                "air_snapshot": data,
                "air_fetched_at": snapshot.fetched_at,
                "air_counts": [
                    {"kind": kind, "label": labels[kind], "count": counts[kind]}
                    for kind in payload.SHOWN_KINDS
                ],
                "air_total": sum(counts.values()),
                "air_config": tab_config(reference, own_layers_for(request.user)),
                "air_kinds": [
                    {"kind": kind, "label": labels[kind]}
                    for kind in payload.SHOWN_KINDS
                ],
                "air_aip_url": payload.AIP_ENR_URL,
                "air_near_km": near_km(),
            }
        )
        return render(request, self.template_name, context)


class AirspaceData(ModelViewPermissionRequiredMixin, View):
    """The current snapshot with its active features. ETag = the snapshot's sha256 (304 on a match)."""

    model = AirspaceFeature

    def get(self, request):
        snapshot = payload.current_snapshot()
        if snapshot is None:
            return JsonResponse({"error": "no_snapshot"}, status=404)
        etag = payload.etag_for(snapshot)
        if payload.etag_matches(request.headers.get("If-None-Match"), etag):
            response = HttpResponseNotModified()
        else:
            response = HttpResponse(
                payload.dumps(payload.build_payload(snapshot)),
                content_type="application/json; charset=utf-8",
            )
        response["ETag"] = etag
        # Always revalidate (cheap: one row and a 304) so a new import shows up at once.
        response["Cache-Control"] = "private, no-cache"
        return response


def _site_entry(center):
    return {
        "id": str(center.pk),
        "code": center.code,
        "name": center.name,
        "lat": float(center.latitude),
        "lon": float(center.longitude),
    }


def _permit_entry(permit):
    radius = permit.radius_km
    return {
        "id": str(permit.pk),
        "number": permit.permission_number,
        "site": permit.cost_center.code,
        "location": permit.location,
        "valid_until": permit.valid_until.isoformat(),
        "lat": float(permit.latitude) if permit.latitude is not None else None,
        "lon": float(permit.longitude) if permit.longitude is not None else None,
        "radius_km": float(radius) if radius is not None else None,
    }


class AirspaceOwnLayers(ModelViewPermissionRequiredMixin, View):
    """The person's own layers for the map: `?layer=sites` or `?layer=permits`.

    «My sites» are the cost centers with coordinates; «Current permits» the approved permits in force
    today with a point (and a circle when they carry a radius). Each layer needs ITS model's view
    permission (403 without it), is cut by the user's tenant, and answers as data: the client draws it
    with `textContent`, and `dumps` escapes markup anyway. Not cached by shared caches."""

    model = AirspaceFeature

    def get(self, request):
        layer = request.GET.get("layer", "")
        if layer not in OWN_LAYERS:
            return JsonResponse({"error": "invalid_layer"}, status=400)
        if not request.user.has_perm(OWN_LAYERS[layer]):
            raise PermissionDenied
        if layer == "sites":
            from apps.registry.models import CostCenter

            rows = scope_queryset_to_tenant(
                CostCenter.objects.filter(
                    is_active=True, latitude__isnull=False, longitude__isnull=False
                ),
                request.user,
            ).order_by("code")
            items = [_site_entry(center) for center in rows]
        else:
            rows = (
                current_permits(request.user)
                .filter(latitude__isnull=False, longitude__isnull=False)
                .select_related("cost_center")
                .order_by("permission_number", "pk")
            )
            items = [_permit_entry(permit) for permit in rows]
        response = HttpResponse(
            payload.dumps({"layer": layer, "items": items}),
            content_type="application/json; charset=utf-8",
        )
        response["Cache-Control"] = "private, no-cache"
        return response


def _number(request, name, low, high):
    raw = request.GET.get(name, "").strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or not (low <= value <= high):
        return None
    return value


def zone_and_aerodrome_features():
    """The active P/R/D/N zones and aerodromes as GeoJSON-like features (what `near/` and `contains` read)."""
    return [
        {
            "type": "Feature",
            "properties": {
                "id": str(row.pk),
                "kind": row.kind,
                "code": row.code,
                "name": row.name,
            },
            "geometry": row.geometry,
        }
        for row in payload.active_features().filter(
            kind__in=payload.ZONE_KINDS + payload.AERODROME_KINDS
        )
    ]


def _entry(item):
    properties = item["feature"]["properties"]
    bearing = item["bearing_deg"]
    return {
        "id": properties["id"],
        "kind": properties["kind"],
        "code": properties["code"],
        "name": properties["name"],
        "distance_km": round(item["distance_km"], 2),
        "distance_nm": round(item["distance_nm"], 2),
        "bearing_deg": None if bearing is None else round(bearing),
    }


class AirspaceNear(ModelViewPermissionRequiredMixin, View):
    """What contains a point, what touches a circle around it and what is near; plus the SIGO text.

    `?lat=&lon=` (decimal degrees) and optionally `&radius_km=`. «Near» is `AIRSPACE_NEAR_KM` and,
    with a circle, it is measured from the circle's edge."""

    model = AirspaceFeature

    def get(self, request):
        lat = _number(request, "lat", -90.0, 90.0)
        lon = _number(request, "lon", -180.0, 180.0)
        if lat is None or lon is None:
            return JsonResponse({"error": "invalid_point"}, status=400)
        radius = 0.0
        if request.GET.get("radius_km", "").strip():
            radius = _number(request, "radius_km", 0.0, MAX_RADIUS_KM)
            if radius is None or radius <= 0:
                return JsonResponse({"error": "invalid_radius"}, status=400)
        close = near_km()
        snapshot = payload.current_snapshot()
        features = zone_and_aerodrome_features()
        found = nearby(
            lat,
            lon,
            features,
            within_km=radius + close,
            aerodromes=NEAREST_AERODROMES,
        )
        containing = [_entry(item) for item in found["containing"]]
        touching = [
            _entry(item) for item in found["within"] if item["distance_km"] <= radius
        ]
        around = [
            _entry(item) for item in found["within"] if item["distance_km"] > radius
        ]
        return JsonResponse(
            {
                "point": {
                    "lat": lat,
                    "lon": lon,
                    "lat_dms": format_dms(lat, "lat"),
                    "lon_dms": format_dms(lon, "lon"),
                },
                "radius_km": radius or None,
                "near_km": close,
                "snapshot": snapshot.sha256 if snapshot else None,
                "containing": containing,
                "touching": touching if radius else [],
                "near": around,
                "aerodromes": [_entry(item) for item in found["aerodromes"]],
            }
        )


class AirspaceAdminLayer(ModelViewPermissionRequiredMixin, View):
    """The «Administrative boundaries» layer (LV-367, phase 6): communes simplified at two levels.

    `?lod=1` (zoom <= 7) or `?lod=2` (zoom >= 8), built once per process from `apps/geo/data/comunas.txt`
    (BCN). ETag = sha256 of that file + the simplification's version, so it only changes with a deploy;
    304 on a match. It is global public cartography, with no tenant: the same for every person, and it
    needs the map's own permission (`view_airspacefeature`, LV-268) like the rest of the screen."""

    model = AirspaceFeature

    def get(self, request):
        try:
            lod = int(request.GET.get("lod", "1"))
        except ValueError:
            lod = 0
        if lod not in administrative_layer.LODS:
            return JsonResponse({"error": "invalid_lod"}, status=400)
        etag = administrative_layer.layer_etag(lod)
        if payload.etag_matches(request.headers.get("If-None-Match"), etag):
            response = HttpResponseNotModified()
        else:
            response = HttpResponse(
                administrative_layer.layer_bytes(lod),
                content_type="application/json; charset=utf-8",
            )
        response["ETag"] = etag
        response["Cache-Control"] = "private, no-cache"
        return response


def _contained_entry(item):
    properties = item["feature"]["properties"]
    return {
        "id": properties["id"],
        "kind": properties["kind"],
        "code": properties["code"],
        "name": properties["name"],
        "relation": item["relation"],
    }


class AirspaceAdminContains(ModelViewPermissionRequiredMixin, View):
    """Which P/R/D/N zones a commune or region contains or touches, and which aerodromes lie inside it.

    `<code>` is a BCN commune code, `r<N>` for a region, or `0` for the «Zona sin demarcar». Computed
    against the FULL rings of the data file (not the simplified drawing) with the pure functions of
    `apps/geo/airspace_geometry.py`. Referential: BCN says so, and its rings come at ~111 m."""

    model = AirspaceFeature

    def get(self, request, code):
        area = administrative_layer.area(code)
        if area is None:
            return JsonResponse({"error": "unknown_area"}, status=404)
        found = features_in_area(zone_and_aerodrome_features(), area["parts"])
        kind_rank = {
            kind: i
            for i, kind in enumerate(payload.AERODROME_KINDS + payload.ZONE_KINDS)
        }
        found.sort(
            key=lambda item: (
                kind_rank.get(item["feature"]["properties"]["kind"], 99),
                item["relation"] != "contained",
                item["feature"]["properties"]["code"] or "~",
                item["feature"]["properties"]["name"],
            )
        )
        entries = [_contained_entry(item) for item in found]
        response = JsonResponse(
            {
                "area": {
                    "code": area["code"],
                    "name": area["name"],
                    "kind": area["kind"],
                    "region": area["region"],
                    "communes": area["communes"],
                },
                "source": administrative_layer.SOURCE_NAME,
                "tolerance_m": administrative_layer.FILE_TOLERANCE_M,
                "zones": [e for e in entries if e["kind"] in payload.ZONE_KINDS],
                "aerodromes": [
                    e for e in entries if e["kind"] in payload.AERODROME_KINDS
                ],
            }
        )
        response["Cache-Control"] = "private, no-cache"
        return response
