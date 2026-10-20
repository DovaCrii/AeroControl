"""What the airspace screen is given (LV-357, phase 3): the JSON of the current snapshot.

Pure shaping, no HTTP. The source's own words (`vertical_limits_text`, `schedule_text`,
`description_text`) travel untouched: they are never converted to numbers, because the paper chart
decides and not this app. The JSON is served as data and drawn by the client with `textContent`;
as a second line of defence `dumps` also escapes `<`, `>` and `&`, so a name that looks like markup
can never reach the page as markup even if some future caller forgets.
"""

import json
import re
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from apps.geo.sections import format_dms

from .models import AirspaceFeature, AirspaceSnapshot

# Drawing aids published as zones ("Medida de círculo", "2 NM"): not airspace, never served.
HIDDEN_KINDS = (AirspaceFeature.KIND_AUX,)
COORD_DECIMALS = 5  # ~1 m: more digits only weigh down the JSON.
STALE_AFTER_DAYS = 30
# AIP-Chile, volume I, section ENR: the official reference for the zones (ENR 5.1).
AIP_ENR_URL = "https://aipchile.dgac.gob.cl/aip/vol1/seccion/enr"

SHOWN_KINDS = tuple(
    kind for kind, _label in AirspaceFeature.KIND_CHOICES if kind not in HIDDEN_KINDS
)
ZONE_KINDS = ("prohibited", "restricted", "danger", "naval")
AERODROME_KINDS = ("aerodrome", "airport")

_FIR_RE = re.compile(r"\bFIR\s+((?:[A-ZÁÉÍÓÚÑ]{2,}(?:\s+|$)){1,2})")


def fir_of(raw_name):
    """The FIR a placemark names ("... FIR SANTIAGO ..." -> "SANTIAGO"), or "".

    Read from the name because the source has no FIR attribute. Best effort: it filters, it never
    decides anything."""
    match = _FIR_RE.search(str(raw_name or ""))
    return " ".join(match.group(1).split()) if match else ""


def ifis_url(feature):
    """The IFIS NOTAM query for an aerodrome with an OACI code (the
    otam_url` pattern, LV-218a).

        A link and not a result, on purpose: the IFIS has no API and a failed parse reads as "no
        advisories"."""
    if feature.kind not in AERODROME_KINDS:
        return ""
    code = (feature.code or "").strip()
    if len(code) != 4 or not code.isalpha():
        return ""
    from apps.operations.models import NOTAM_QUERY_BASE

    return f"{NOTAM_QUERY_BASE}?designador={quote(code)}&metodo=designador"


def _round(value):
    if isinstance(value, (list, tuple)):
        return [_round(item) for item in value]
    if isinstance(value, float):
        return round(value, COORD_DECIMALS)
    return value


def near_km():
    """«Near» in kilometres (the person's decision of 2026-10-20; `AIRSPACE_NEAR_KM`)."""
    return float(getattr(settings, "AIRSPACE_NEAR_KM", 10))


def current_snapshot():
    return AirspaceSnapshot.objects.filter(is_current=True).first()


def active_features():
    """Active (not archived) features of the map, drawing aids excluded."""
    return AirspaceFeature.objects.filter(is_active=True).exclude(kind__in=HIDDEN_KINDS)


def etag_for(snapshot):
    return f'"{snapshot.sha256}"'


def etag_matches(header, etag):
    """`If-None-Match` may carry several validators and weak ones (`W/"..."`)."""
    if not header:
        return False
    wanted = etag.strip('"')
    for token in header.split(","):
        token = token.strip()
        if token == "*" or token.removeprefix("W/").strip('"') == wanted:
            return True
    return False


def feature_payload(feature):
    point = (feature.geometry or {}).get("type") == "Point"
    data = {
        "id": str(feature.pk),
        "kind": feature.kind,
        "code": feature.code,
        "name": feature.name,
        "folder": feature.folder,
        "fir": fir_of(feature.raw_name),
        "region": feature.region,
        "commune": feature.commune,
        "lat": round(feature.center_lat, COORD_DECIMALS),
        "lon": round(feature.center_lon, COORD_DECIMALS),
        "dms": f"{format_dms(feature.center_lat, 'lat')} {format_dms(feature.center_lon, 'lon')}",
        "vertical": feature.vertical_limits_text,
        "schedule": feature.schedule_text,
        "text": feature.description_text,
    }
    if not point:
        data["bbox"] = _round(
            [feature.min_lon, feature.min_lat, feature.max_lon, feature.max_lat]
        )
        data["geometry"] = {
            "type": feature.geometry.get("type"),
            "coordinates": _round(feature.geometry.get("coordinates")),
        }
    url = ifis_url(feature)
    if url:
        data["ifis"] = url
    return data


def snapshot_payload(snapshot, now=None):
    now = now or timezone.now()
    age = (now - snapshot.fetched_at).days
    return {
        "id": str(snapshot.pk),
        "source_name": snapshot.source_name,
        "source_url": snapshot.source_url,
        "attribution": snapshot.attribution,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "sha256": snapshot.sha256,
        "age_days": age,
        "stale": age > STALE_AFTER_DAYS,
    }


def build_payload(snapshot, now=None):
    features = [
        feature_payload(f) for f in active_features().order_by("kind", "code", "name")
    ]
    return {"snapshot": snapshot_payload(snapshot, now), "features": features}


def dumps(payload):
    """Compact JSON with `<`, `>` and `&` escaped, so it is inert even if inlined in HTML."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
