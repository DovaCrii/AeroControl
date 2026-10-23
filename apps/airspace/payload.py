"""What the airspace screen is given (LV-357, phase 3): the JSON of the current snapshot.

Pure shaping, no HTTP. The source's own words (`vertical_limits_text`, `schedule_text`,
`description_text`) travel untouched: they are never converted to numbers, because the paper chart
decides and not this app. The JSON is served as data and drawn by the client with `textContent`;
as a second line of defence `dumps` also escapes `<`, `>` and `&`, so a name that looks like markup
can never reach the page as markup even if some future caller forgets.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from apps.geo.sections import format_dms

from .aip_import import ATTRIBUTION, threshold_m
from .aip_review import active_aip_features as _published_aip_features
from .models import (
    REVIEW_APPROVED,
    SOURCE_AIP_ENR51,
    SOURCE_GOOGLE,
    STATUS_PUBLISHED,
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)

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
    """The published Google copy: until an AIP copy is approved (LV-361), the screen shows this one."""
    return AirspaceSnapshot.objects.filter(
        is_current=True, source_kind=SOURCE_GOOGLE, status=STATUS_PUBLISHED
    ).first()


def active_features():
    """Active (not archived) features of the map, drawing aids excluded."""
    return AirspaceFeature.objects.filter(
        is_active=True,
        source_kind=SOURCE_GOOGLE,
        review_status=REVIEW_APPROVED,
    ).exclude(kind__in=HIDDEN_KINDS)


def aip_snapshot():
    """The published, current AIP copy (LV-361), or `None`: until a person approves and publishes one,
    the screen is exactly what it was with the Google map alone."""
    return AirspaceSnapshot.objects.filter(
        is_current=True, source_kind=SOURCE_AIP_ENR51, status=STATUS_PUBLISHED
    ).first()


def active_aip_features():
    """The approved zones of the published AIP copy: the ONLY AIP rows that are ever served."""
    return _published_aip_features().exclude(kind__in=HIDDEN_KINDS)


# What a Google feature is once an AIP copy is published (LV-361, phase 5): the zones the AIP has
# are drawn from the AIP and the Google shape of the same code steps back to the reference layer
# (shadowed); the Google zones the AIP does not carry (SC-D12, SC-P77, the naval ones) go to that
# same reference layer too; everything else of Google (aerodromes, airstrips, FIR) stays as it was.
ROLE_PRIMARY = "primary"
ROLE_SHADOWED = "shadowed"
ROLE_REFERENCE = "reference"
AIP_FOLDER = "AIP-Chile ENR 5.1"  # the folder filter doubles as a source filter


def has_shape(geometry):
    """True when a geometry has something to draw (an empty collection is a zone given only as text)."""
    if not isinstance(geometry, dict):
        return False
    if geometry.get("type") == "GeometryCollection":
        return any(has_shape(part) for part in geometry.get("geometries") or [])
    return bool(geometry.get("coordinates"))


@dataclass
class Served:
    """What the screen is given: the Google rows with their role and, if published, the AIP rows."""

    aip: AirspaceSnapshot | None = None
    aip_rows: list = field(default_factory=list)
    google_rows: list = field(default_factory=list)  # [(feature, role)]

    def searchable(self):
        """Every feature that is listed, counted and searched. A Google shape hidden behind the AIP's
        own is the same zone twice: it is only a reference drawing, never a second result."""
        return self.aip_rows + [
            f for f, role in self.google_rows if role != ROLE_SHADOWED
        ]


def served_set():
    google = list(active_features().order_by("kind", "code", "name"))
    aip = aip_snapshot()
    if aip is None:
        return Served(None, [], [(f, ROLE_PRIMARY) for f in google])
    rows = list(active_aip_features().order_by("kind", "code", "name"))
    codes = {f.code for f in rows if f.code}
    tagged = []
    for feature in google:
        if feature.kind not in ZONE_KINDS:
            role = ROLE_PRIMARY
        elif feature.code and feature.code in codes:
            role = ROLE_SHADOWED
        else:
            role = ROLE_REFERENCE
        tagged.append((feature, role))
    return Served(aip, rows, tagged)


def _amdt_number(value):
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def aip_freshness(aip):
    """The latest amendment this system knows of and whether the published copy is older.

    «Known» is only what the `AirspaceSnapshot` table says: the highest `amdt_number` among the AIP
    snapshots (a newer draft counts, it proves the amendment exists). It is NOT looked up anywhere:
    when there is no other snapshot the copy's own amendment is the latest known one."""
    own = _amdt_number(aip.amdt_number)
    best, best_date = own, aip.effective_date
    for amdt, effective in AirspaceSnapshot.objects.filter(
        source_kind=aip.source_kind
    ).values_list("amdt_number", "effective_date"):
        number = _amdt_number(amdt)
        if number is not None and (best is None or number > best):
            best, best_date = number, effective
    return {
        "latest_known_amdt": "" if best is None else str(best),
        "latest_known_date": best_date.isoformat() if best_date else "",
        "outdated": own is not None and best is not None and own < best,
    }


def aip_attribution(aip):
    """The attribution text in the language of the request (it is not the one stored at import)."""
    date = (
        aip.effective_date.strftime("%d %b %Y").upper() if aip.effective_date else "?"
    )
    return str(ATTRIBUTION) % {"amdt": aip.amdt_number or "?", "date": date}


def aip_payload(aip):
    return {
        "amdt": aip.amdt_number,
        "effective_date": aip.effective_date.isoformat() if aip.effective_date else "",
        "attribution": aip_attribution(aip),
        "threshold_m": threshold_m(),
        **aip_freshness(aip),
    }


def cross_checks(aip, rows):
    """`{aip feature pk: {"m": metres, "verdict": None | "match" | "discrepancy"}}`.

    The distance is the largest of the AIP outline's vertices to the Google outline. Only pairs whose
    Google shape is still the current one are used. `verdict` stays `None` until the person fixes
    `AIRSPACE_CROSSCHECK_THRESHOLD_M`: what counts as a discrepancy is theirs to say."""
    limit = threshold_m()
    out = {}
    pairs = AirspaceCrossCheck.objects.filter(
        snapshot=aip,
        aip_feature__in=[row.pk for row in rows],
        google_feature__isnull=False,
        google_feature__is_active=True,
        google_feature__snapshot__is_current=True,
        max_vertex_m__isnull=False,
    ).values_list("aip_feature_id", "max_vertex_m")
    for pk, metres in pairs:
        verdict = None
        if limit is not None:
            verdict = "discrepancy" if metres > limit else "match"
        out[pk] = {"m": round(metres), "verdict": verdict}
    return out


def etag_for(snapshot, aip=None):
    """The validator of `data.json`: the sha256 of the Google photo; once an AIP copy is published,
    a digest of BOTH photos (it changes when either changes) plus what else shapes the answer."""
    if aip is None:
        return f'"{snapshot.sha256}"'
    limit = threshold_m()
    parts = [
        snapshot.sha256,
        aip.sha256,
        aip_freshness(aip)["latest_known_amdt"],
        "" if limit is None else repr(limit),
    ]
    return '"' + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest() + '"'


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


def public_geometry(geometry):
    """The geometry as the client receives it, coordinates rounded.

    A `GeometryCollection` (a KML `MultiGeometry`: a zone with its label point, as SC-P29) carries
    its parts in `geometries`, not in `coordinates`. Serving only `coordinates` sent `null`, Leaflet
    threw while drawing and the whole map stayed dead (LV-363)."""
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        return {
            "type": kind,
            "geometries": [
                public_geometry(g) for g in geometry.get("geometries") or []
            ],
        }
    return {"type": kind, "coordinates": _round(geometry.get("coordinates"))}


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
        data["geometry"] = public_geometry(feature.geometry)
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


def aip_feature_payload(feature, cross=None):
    """A zone of the AIP. A zone approved «only as text» (an arc or a sector: the AIP gives no centre
    for it) carries no point and no geometry, only `no_shape`: the client lists and searches it but
    never draws it, and the server never invents the missing centre."""
    shaped = has_shape(feature.geometry)
    data = {
        "id": str(feature.pk),
        "kind": feature.kind,
        "code": feature.code,
        "name": feature.name,
        "folder": AIP_FOLDER,
        "fir": fir_of(feature.raw_name),
        "region": feature.region,
        "commune": feature.commune,
        "lat": round(feature.center_lat, COORD_DECIMALS) if shaped else None,
        "lon": round(feature.center_lon, COORD_DECIMALS) if shaped else None,
        "dms": (
            f"{format_dms(feature.center_lat, 'lat')} {format_dms(feature.center_lon, 'lon')}"
            if shaped
            else ""
        ),
        "vertical": feature.vertical_limits_text,
        "schedule": feature.schedule_text,
        "text": feature.lateral_text,
        "source_kind": SOURCE_AIP_ENR51,
    }
    if shaped:
        data["bbox"] = _round(
            [feature.min_lon, feature.min_lat, feature.max_lon, feature.max_lat]
        )
        data["geometry"] = public_geometry(feature.geometry)
    else:
        data["no_shape"] = feature.geometry_method or "unreadable"
    if cross:
        data["cross"] = cross
    return data


def build_payload(snapshot, now=None, served=None):
    served = served or served_set()
    data = {"snapshot": snapshot_payload(snapshot, now)}
    if not served.aip:
        # No published AIP copy: byte for byte what the screen always served.
        data["features"] = [feature_payload(f) for f, _role in served.google_rows]
        return data
    crosses = cross_checks(served.aip, served.aip_rows)
    features = [aip_feature_payload(f, crosses.get(f.pk)) for f in served.aip_rows]
    for feature, role in served.google_rows:
        item = feature_payload(feature)
        item["source_kind"] = SOURCE_GOOGLE
        if role != ROLE_PRIMARY:
            item["ref"] = True
        if role == ROLE_SHADOWED:
            item["shadowed"] = True
        features.append(item)
    data["snapshot"]["aip"] = aip_payload(served.aip)
    data["features"] = features
    return data


def dumps(payload):
    """Compact JSON with `<`, `>` and `&` escaped, so it is inert even if inlined in HTML."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
