"""The «Airspace» tab of the Environment section (LV-357, phase 3) and its two data endpoints.

* `AirspaceTab`   GET /environment/airspace/            the screen (404 with an import guide if no snapshot)
* `AirspaceData`  GET /environment/airspace/data.json   the current snapshot as JSON (ETag = its sha256)
* `AirspaceNear`  GET /environment/airspace/near/       what contains / is near a point or circle

All three need `view_airspacefeature` (LV-268). The catalog is global (no tenant), like `Aerodrome`.
`near/` runs the very same pure functions as `apps/geo/airspace_geometry.py`, so the client never
re-implements the distance maths that decides "this zone touches your circle".

What this screen never says: "you can fly", a buffer or minimum distance nobody wrote, a vertical
limit converted to a number, or that a zone "is active now". The source's words travel as written.
"""

import math

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.core.views import ModelViewPermissionRequiredMixin
from apps.environment.views import EnvironmentTab, environment_context
from apps.geo.airspace_geometry import nearby
from apps.geo.sections import format_dms

from . import payload
from .models import AirspaceFeature

MAX_RADIUS_KM = 1000.0
NEAREST_AERODROMES = 3


def near_km():
    """«Near» in kilometres (the person's decision of 2026-10-20; `AIRSPACE_NEAR_KM`)."""
    return float(getattr(settings, "AIRSPACE_NEAR_KM", 10))


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
        "measureHint": _("Click the map to add points. Press Escape to stop."),
        "circleHint": _("Click the map to place the centre of the circle."),
        "nearHint": _("Click the map to ask what is around that point."),
        "invalidCoordinate": _("That coordinate is not valid: {reason}."),
        "reasonLat": _("latitude outside -90 to 90"),
        "reasonLon": _("longitude outside -180 to 180"),
        "reasonMinutes": _("minutes and seconds must be below 60"),
        "reasonSign": _("use a sign or a hemisphere letter, not both"),
        "reasonAxis": _("one latitude and one longitude are needed"),
        "loading": _("Loading the map data"),
        "loadFailed": _(
            "The map data could not be loaded. Reload the page to try again."
        ),
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
    }


def tab_config(reference):
    return {
        "dataUrl": reverse("airspace-data"),
        "nearUrl": reverse("airspace-near"),
        "nearKm": near_km(),
        "tileProviders": settings.GEO_TILE_PROVIDERS,
        "reference": reference,
        "kinds": kind_labels(),
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
                "air_config": tab_config(reference),
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


def _number(request, name, low, high):
    raw = request.GET.get(name, "").strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or not (low <= value <= high):
        return None
    return value


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
        features = [
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
