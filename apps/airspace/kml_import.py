"""LV-357: read the airspace map (a KML) into classified features, and sync them.

The map is the "ZONAS SENSIBLES" Google My Maps that the DGAC delivers; the person
confirmed (2026-10-20) it is the only official source for now, though raw. Its
license is **not** confirmed and the repo is public, so the data never goes to
git: it is imported into the database by `import_airspace_zones`, and tests use a
synthetic KML.

Two stages, so the first is pure and testable without a database:

1. `parse_airspace_kml(bytes)` -> `ParseResult`: hardened parse (the DOCTYPE
   guard and the entity-free parser of `apps.geo.kml.parse`), closes circles that
   arrive as closed LineStrings, normalizes zone codes (`SC - R54` -> `SC-R54`),
   classifies `kind`, turns the HTML descriptions into plain text.
2. `sync_features(...)`: compares against the active rows and writes a new
   snapshot. What disappears is **archived**, never deleted.

Nothing here decides whether a flight is allowed: vertical limits and schedules
are the source's own words, copied, not converted.
"""

import hashlib
import json
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from apps.geo.administrative import locate
from apps.geo.kml.errors import KmlImportError
from apps.geo.kml.parse import parse_kml_bytes

from .models import AirspaceFeature, AirspaceSnapshot

DEFAULT_URL = (
    "https://www.google.com/maps/d/kml?mid=1T3wWBnClwim-qP1isEKxBO4Xc1Dt6z4&forcekml=1"
)
MAX_BYTES = 16 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30

# Stored in Spanish (it is data shown next to the map). The source string is
# English; the Spanish lives in the catalog.
ATTRIBUTION = _("Sensitive-zones map delivered by the DGAC (Google My Maps)")


class AirspaceFetchError(Exception):
    """The source could not be downloaded; the current snapshot is untouched."""


# ── text helpers ────────────────────────────────────────────────────────────


def fold(text):
    """Lower-case without accents, for comparing names and folders."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


class _TextExtractor(HTMLParser):
    _BREAKS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "table"}
    _SKIPPED = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIPPED:
            self._skip += 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIPPED:
            self._skip = max(0, self._skip - 1)
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


# Lines that Google My Maps writes for empty ExtendedData columns.
_EMPTY_FIELD_LINE = re.compile(
    r"^(descripci[oó]n|description|tracking_href\w*|gx_media_links)\s*:\s*$", re.I
)
MAX_TEXT = 20000


def html_to_text(html):
    """Plain text from the source's HTML. Tags and scripts are dropped, never kept."""
    extractor = _TextExtractor()
    # `HTMLParser` tolerates malformed markup; a stray tag never stops an import.
    extractor.feed(html or "")
    extractor.close()
    lines = []
    for raw in "".join(extractor.parts).replace("\xa0", " ").splitlines():
        line = " ".join(raw.split())
        if _EMPTY_FIELD_LINE.match(line):
            continue
        if not line and (not lines or not lines[-1]):
            continue
        lines.append(line)
    return "\n".join(lines).strip()[:MAX_TEXT]


_VERTICAL = re.compile(
    r"(l[ií]mites?\s+verticales?|\bFT\b|\bFL\s?\d+|\bUNL\b|\bGND\b|\bSFC\b)", re.I
)
_VERTICAL_LABEL = re.compile(r"^l[ií]mites?\s+verticales?\s*:?$", re.I)
_SCHEDULE = re.compile(
    r"(\bH24\b|\bHJ\b|\bHX\b|\bhorario\b|\bpermanente\b|\bNOTAM\b|\bactivad[ao]\b)",
    re.I,
)
_SCHEDULE_LABEL = re.compile(r"^horario\s*:?$", re.I)


def extract_limits(description_text):
    """(vertical, schedule) as the source wrote them. Heuristic by keywords, no conversion.

    The first lines that mention altitudes or flight levels, and the ones that
    mention a schedule. A label alone on its line ("HORARIO:") takes the next
    non-empty line with it.
    """
    vertical, schedule = [], []
    lines = [line for line in description_text.splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        line = lines[index]
        target = None
        if _VERTICAL_LABEL.match(line):
            target = vertical
        elif _SCHEDULE_LABEL.match(line):
            target = schedule
        elif _VERTICAL.search(line):
            target = vertical
        elif _SCHEDULE.search(line):
            target = schedule
        if target is not None:
            target.append(line)
            if (
                _VERTICAL_LABEL.match(line) or _SCHEDULE_LABEL.match(line)
            ) and index + 1 < len(lines):
                target.append(lines[index + 1])
                index += 1
        index += 1
    return " / ".join(vertical), " / ".join(schedule)


# ── codes ───────────────────────────────────────────────────────────────────

_ZONE_CODE = re.compile(
    r"(?<![A-Za-z])SC\s*[-–—]?\s*([PRD])\s*[-–—]?\s*(\d{1,3})(?!\d)"
)
_OACI_START = re.compile(r"^(SC[A-Z0-9]{2})\b")
_OACI_ANYWHERE = re.compile(r"\b(SC[A-Z]{2})\b")


def normalize_zone_code(text):
    """`SC-P29` from any spelling ("SC - R54", "SC R-41", "SC – P 30"), or ''."""
    match = _ZONE_CODE.search(text or "")
    return f"SC-{match.group(1)}{int(match.group(2))}" if match else ""


def _oaci(name, *, anywhere):
    text = (name or "").strip()
    match = _OACI_START.match(text)
    if not match and anywhere:
        match = _OACI_ANYWHERE.search(text)
    return match.group(1) if match else ""


_AUX_NAME = re.compile(
    r"^(medida de circulo|punto centrado|\d+([.,]\d+)?\s*nm$|\d{1,3}\s*[º°o]\s*\d)"
)
_ZONE_KINDS = {
    "P": AirspaceFeature.KIND_PROHIBITED,
    "R": AirspaceFeature.KIND_RESTRICTED,
    "D": AirspaceFeature.KIND_DANGER,
}


def classify(folder, name):
    """(kind, code, warning) for a placemark, from its folder and its name.

    The style of the source does not encode the type: it comes from the folder
    and the zone code. Anything that is not clearly a zone, an aerodrome or a
    FIR line is a drawing aid (`aux`) and the import says so.
    """
    folder_key, name_key = fold(folder), fold(name)
    zone = normalize_zone_code(name)
    if _AUX_NAME.match(name_key):
        return AirspaceFeature.KIND_AUX, "", ""
    if folder_key.startswith("aerodromos"):
        code = _oaci(name, anywhere=True)
        is_airport = re.search(r"\b(ap|aeropuerto)\b", name_key) is not None
        kind = (
            AirspaceFeature.KIND_AIRPORT
            if is_airport
            else AirspaceFeature.KIND_AERODROME
        )
        return kind, code, "" if code else "aerodrome without an ICAO code"
    if folder_key.startswith("pistas"):
        return AirspaceFeature.KIND_AIRSTRIP, _oaci(name, anywhere=True), ""
    if folder_key.startswith("armada"):
        return AirspaceFeature.KIND_NAVAL, zone, ""
    if zone:
        return _ZONE_KINDS[zone[3]], zone, ""
    if folder_key.startswith("region"):
        return AirspaceFeature.KIND_FIR_BOUNDARY, "", ""
    return AirspaceFeature.KIND_AUX, "", "zone without a code kept as a drawing aid"


# ── geometry ────────────────────────────────────────────────────────────────


def _round_point(point):
    return [round(float(point[0]), 6), round(float(point[1]), 6)]


def _convert_geometry(geometry):
    """GeoJSON (lon, lat, no altitude) from the canonical geometry, or None.

    A LineString whose last vertex repeats the first (4+ vertices) is a ring:
    circles arrive that way (Trimble, My Maps) and become a Polygon. An open
    line stays a line.
    """
    if not geometry:
        return None
    kind = geometry.get("type")
    if kind == "Point":
        coords = geometry.get("coordinates") or []
        return (
            {"type": "Point", "coordinates": _round_point(coords)} if coords else None
        )
    if kind == "LineString":
        coords = [_round_point(p) for p in geometry.get("coordinates") or []]
        if len(coords) < 2:
            return None
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return {"type": "Polygon", "coordinates": [coords]}
        return {"type": "LineString", "coordinates": coords}
    if kind == "Polygon":
        rings = [[_round_point(p) for p in ring] for ring in geometry["coordinates"]]
        rings = [ring for ring in rings if len(ring) >= 4]
        return {"type": "Polygon", "coordinates": rings} if rings else None
    if kind == "GeometryCollection":
        parts = [_convert_geometry(g) for g in geometry.get("geometries") or []]
        parts = [p for p in parts if p]
        return {"type": "GeometryCollection", "geometries": parts} if parts else None
    return None


def _points(geometry):
    kind = geometry["type"]
    if kind == "Point":
        yield geometry["coordinates"]
    elif kind == "LineString":
        yield from geometry["coordinates"]
    elif kind == "Polygon":
        for ring in geometry["coordinates"]:
            yield from ring
    else:
        for part in geometry["geometries"]:
            yield from _points(part)


def bounds_of(geometry):
    """(min_lat, max_lat, min_lon, max_lon) or None if a coordinate is out of range."""
    points = list(_points(geometry))
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    if not points or min(lats) < -90 or max(lats) > 90:
        return None
    if min(lons) < -180 or max(lons) > 180:
        return None
    return min(lats), max(lats), min(lons), max(lons)


# ── parsing ─────────────────────────────────────────────────────────────────


@dataclass
class ParsedFeature:
    source_key: str
    content_hash: str
    kind: str
    code: str
    name: str
    raw_name: str
    folder: str
    description_text: str
    vertical_limits_text: str
    schedule_text: str
    geometry: dict
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    center_lat: float
    center_lon: float
    region: str = ""
    commune: str = ""


@dataclass
class ParseResult:
    document_name: str = ""
    features: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _placemarks(nodes, folder=""):
    for node in nodes:
        if node["kind"] == "folder":
            yield from _placemarks(node["children"], node["name"])
        elif node["kind"] == "placemark":
            yield folder, node


def _digest(*parts):
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def parse_airspace_kml(data):
    """Bytes -> `ParseResult`. Raises `KmlImportError` on a bad or hostile file."""
    document = parse_kml_bytes(data)
    result = ParseResult(document_name=(document.get("name") or "").strip())
    seen = {}
    skipped = closed = 0
    for folder, node in _placemarks(document["children"]):
        raw_name = (node["name"] or "").strip()
        geometry = _convert_geometry(node["geometry"])
        bounds = bounds_of(geometry) if geometry else None
        if bounds is None:
            skipped += 1
            result.warnings.append(f"skipped without a usable geometry: {raw_name!r}")
            continue
        if (node["geometry"] or {}).get("type") == "LineString" and (
            geometry["type"] == "Polygon"
        ):
            closed += 1
        name = " ".join(raw_name.split())[:300]
        kind, code, warning = classify(folder, name)
        if warning:
            result.warnings.append(f"{warning}: {name!r}")
        text = html_to_text(node["description"])
        vertical, schedule = extract_limits(text)

        identity = _digest(fold(folder), fold(name))
        ordinal = seen.get(identity, 0)
        seen[identity] = ordinal + 1
        if ordinal:
            result.warnings.append(f"duplicate name in the same folder: {name!r}")
        min_lat, max_lat, min_lon, max_lon = bounds
        if geometry["type"] == "Point":
            center_lon, center_lat = geometry["coordinates"]
        else:
            center_lat = round((min_lat + max_lat) / 2, 6)
            center_lon = round((min_lon + max_lon) / 2, 6)
        content = json.dumps(
            [kind, code, name, folder, text, vertical, schedule, geometry],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result.features.append(
            ParsedFeature(
                source_key=_digest(identity, str(ordinal)),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                kind=kind,
                code=code,
                name=name,
                raw_name=raw_name[:500],
                folder=" ".join(folder.split())[:200],
                description_text=text,
                vertical_limits_text=vertical,
                schedule_text=schedule,
                geometry=geometry,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                center_lat=center_lat,
                center_lon=center_lon,
            )
        )
    if closed:
        result.warnings.append(f"{closed} closed line(s) converted to polygons")
    if not result.features:
        raise KmlImportError("The KML has no placemark with a usable geometry.")
    return result


def locate_points(features):
    """Region and commune for point features only (a zone has no single commune)."""
    for feature in features:
        if feature.geometry["type"] != "Point":
            continue
        place = locate(feature.center_lat, feature.center_lon)
        if place:
            feature.region = (place.get("region") or "")[:120]
            feature.commune = (place.get("comuna") or "")[:120]


# ── download ────────────────────────────────────────────────────────────────


def fetch_url(url, timeout=DOWNLOAD_TIMEOUT_SECONDS):
    """Download the KML. The only place the app reaches out for this data."""
    if urlparse(url).scheme not in {"http", "https"}:
        raise AirspaceFetchError("Only http(s) URLs are accepted.")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        url, headers={"User-Agent": "AeroControl-airspace-import"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise AirspaceFetchError(
            f"The source did not answer ({type(exc).__name__}). "
            "The current snapshot was not touched."
        ) from exc
    if len(data) > MAX_BYTES:
        raise AirspaceFetchError("The source is larger than the allowed size.")
    return data


# ── sync ────────────────────────────────────────────────────────────────────


@dataclass
class SyncReport:
    unchanged: bool = False
    dry_run: bool = False
    added: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    archived: list = field(default_factory=list)
    total: int = 0
    snapshot: object = None


def sync_features(
    result, *, sha256, source_name, source_url="", dry_run=False, now=None
):
    """Compare with the active rows; write a new snapshot unless nothing changed.

    Same sha256 as the current snapshot -> nothing is read or written. Otherwise
    a feature is *added* (key not active), *changed* (same key, different
    content: the old row is archived and a new one created, so history stays),
    or *archived* (key gone from the source).
    """
    current = AirspaceSnapshot.objects.filter(is_current=True).first()
    if current and current.sha256 == sha256:
        return SyncReport(unchanged=True, dry_run=dry_run, total=current.feature_count)

    existing = {f.source_key: f for f in AirspaceFeature.objects.filter(is_active=True)}
    report = SyncReport(dry_run=dry_run, total=len(result.features))
    incoming = {f.source_key: f for f in result.features}
    to_create = []
    for feature in result.features:
        old = existing.get(feature.source_key)
        if old is None:
            report.added.append(feature)
            to_create.append(feature)
        elif old.content_hash != feature.content_hash:
            report.changed.append(feature)
            to_create.append(feature)
    report.archived = [f for key, f in existing.items() if key not in incoming]
    if dry_run:
        return report

    locate_points(to_create)
    with transaction.atomic():
        if current:
            current.is_current = False
            current.save(update_fields=["is_current", "updated_at"])
        with translation.override("es"):
            attribution = str(ATTRIBUTION)
        snapshot = AirspaceSnapshot.objects.create(
            source_name=source_name[:200],
            source_url=source_url[:500],
            fetched_at=now or timezone.now(),
            sha256=sha256,
            feature_count=len(result.features),
            attribution=attribution,
            added=len(report.added),
            changed=len(report.changed),
            archived=len(report.archived),
            is_current=True,
        )
        retired = [f.pk for f in report.archived] + [
            existing[f.source_key].pk for f in report.changed
        ]
        if retired:
            AirspaceFeature.objects.filter(pk__in=retired).update(
                is_active=False, archived_in=snapshot, updated_at=timezone.now()
            )
        AirspaceFeature.objects.bulk_create(
            AirspaceFeature(snapshot=snapshot, **vars(feature)) for feature in to_create
        )
    report.snapshot = snapshot
    return report
