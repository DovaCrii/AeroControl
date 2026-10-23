"""LV-361, phase 3: turn the ENR 5.1 PDF into a DRAFT snapshot of the airspace catalog.

The PDF is read by `aip_pdf` (words with a bounding box) and understood by `aip_parser` (pure
functions); this module is the only one that writes. Rules, all of them on purpose:

* **Nothing is published here.** The snapshot is born `draft`, its features are born inactive
  (`is_active=False`) and `pending` / `needs_review`, so no query that serves the map can see them
  before a person approves them (phase 4). The Google snapshot stays the current one.
* **Idempotent by the SHA-256 of the PDF.** The same file again does nothing; a new file makes a new
  snapshot. A zone whose source content did not change keeps the decision a person already took
  (approved or rejected, with the geometry they corrected); a changed or new one starts pending.
* **Nothing is deleted.** An unpublished snapshot that a newer one replaces is marked `rejected` and
  its features point at the newer one (`archived_in`). What the next publication retires from the
  current snapshot is archived then, in one transaction with the publication.
* **No personal data.** The remarks column carries names, phones and e-mails of officials; the
  parser scrubs them before anything arrives here, and no PDF text is kept except the scrubbed one.
* **The cross-check measures, it does not judge** until the person sets
  `AIRSPACE_CROSSCHECK_THRESHOLD_M`.
"""

import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass, field
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from apps.geo.airspace_geometry import vertex_distances_m

from . import aip_parser, aip_pdf, kml_import
from .models import (
    GEOMETRY_METHODS,
    REVIEW_APPROVED,
    REVIEW_NEEDS_REVIEW,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    SOURCE_AIP_ENR51,
    SOURCE_GOOGLE,
    STATUS_DRAFT,
    STATUS_IN_REVIEW,
    STATUS_PUBLISHED,
    STATUS_REJECTED,
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)

SOURCE_NAME = "AIP-Chile ENR 5.1"
_BASE = (
    "https://aipchile.dgac.gob.cl/dasa/aip_chile_con_contenido/ais/2%20ENR%20Parte%202/"
)
DEFAULT_URL = (
    _BASE
    + quote("ENR 5 Zonas Prohibidas, Restringidas y Peligrosas", safe="")
    + "/"
    + quote("ENR 5.1-1 Zonas P, R, D.pdf", safe="")
)
MAX_BYTES = kml_import.MAX_BYTES
DOWNLOAD_TIMEOUT_SECONDS = kml_import.DOWNLOAD_TIMEOUT_SECONDS

ATTRIBUTION = _(
    "Source: AIP-Chile, DGAC, AMDT NR %(amdt)s (%(date)s), ENR 5.1. "
    "For reference only; check the current NOTAM/SUP."
)

KIND_OF_LETTER = {
    "P": AirspaceFeature.KIND_PROHIBITED,
    "R": AirspaceFeature.KIND_RESTRICTED,
    "D": AirspaceFeature.KIND_DANGER,
}
ZONE_KINDS = tuple(KIND_OF_LETTER.values())
EMPTY_GEOMETRY = {"type": "GeometryCollection", "geometries": []}
PENDING_STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW)


class AipImportError(Exception):
    """The PDF could not be turned into a snapshot; nothing was written."""


# ── reading ─────────────────────────────────────────────────────────────────


@dataclass
class ParsedPdf:
    sha256: str
    amdt_number: str
    effective_date: object
    zones: list
    summary: dict


def fetch_pdf(url, timeout=DOWNLOAD_TIMEOUT_SECONDS):
    """Download the PDF. The only place the app reaches out for this data."""
    try:
        return kml_import.fetch_url(url, timeout=timeout)
    except kml_import.AirspaceFetchError as exc:
        raise AipImportError(str(exc)) from exc


def parse_pdf(data):
    """Bytes -> `ParsedPdf`. Raises `AipImportError` on anything that is not a usable ENR 5.1."""
    if len(data) > MAX_BYTES:
        raise AipImportError("The file is larger than the allowed size.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise AipImportError("The file is not a PDF.")
    try:
        pages = aip_pdf.read_pages(io.BytesIO(data))
    except aip_pdf.PdfSupportMissing as exc:
        raise AipImportError(
            "Reading the PDF needs the optional package pdfplumber (uv pip install pdfplumber)."
        ) from exc
    except aip_pdf.PdfUnreadable as exc:
        raise AipImportError(str(exc)) from exc
    zones, summary = aip_parser.parse_enr51_words(pages)
    if not zones:
        raise AipImportError(
            "No zones were found in the PDF: it does not look like ENR 5.1."
        )
    amdt, effective = aip_parser.extract_amendment(pages)
    return ParsedPdf(
        sha256=hashlib.sha256(data).hexdigest(),
        amdt_number=amdt,
        effective_date=effective,
        zones=zones,
        summary=summary,
    )


# ── zones -> feature rows ───────────────────────────────────────────────────


def _digest(*parts):
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass
class ZoneRow:
    """One zone ready to be written (no database object yet)."""

    source_key: str
    content_hash: str
    kind: str
    code: str
    name: str
    folder: str
    vertical_limits_text: str
    schedule_text: str
    lateral_text: str
    geometry: dict
    geometry_method: str
    parse_warnings: list
    review_status: str
    min_lat: float = 0.0
    max_lat: float = 0.0
    min_lon: float = 0.0
    max_lon: float = 0.0
    center_lat: float = 0.0
    center_lon: float = 0.0
    reviewed_by_id: object = None
    reviewed_at: object = None
    carried: bool = False

    @property
    def has_geometry(self):
        return bool(self.geometry.get("coordinates"))

    def set_bounds(self):
        bounds = kml_import.bounds_of(self.geometry) if self.has_geometry else None
        if bounds is None:
            self.min_lat = self.max_lat = self.min_lon = self.max_lon = 0.0
            self.center_lat = self.center_lon = 0.0
            return
        self.min_lat, self.max_lat, self.min_lon, self.max_lon = bounds
        self.center_lat = round((bounds[0] + bounds[1]) / 2, 6)
        self.center_lon = round((bounds[2] + bounds[3]) / 2, 6)


def rows_from_zones(zones):
    """`ZoneRow`s for the parsed zones, keyed so that a zone is the same zone across amendments."""
    rows, seen = [], {}
    for zone in zones:
        code = zone["code"]
        name = zone["name"] or code or "-"
        identity = _digest(SOURCE_AIP_ENR51, code or kml_import.fold(name))
        ordinal = seen.get(identity, 0)
        seen[identity] = ordinal + 1
        geometry = zone["geometry"] or EMPTY_GEOMETRY
        method = zone["geometry_method"]
        warnings = list(zone["warnings"])
        if ordinal:
            warnings.append(
                f"duplicate_zone: {code or name!r} appears {ordinal + 1} times in the PDF"
            )
        content = json.dumps(
            [
                zone["kind"],
                code,
                name,
                zone["lateral_text"],
                zone["vertical_text"],
                zone["remarks_text"],
                geometry,
                method,
            ],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        row = ZoneRow(
            source_key=_digest(identity, str(ordinal)),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            kind=KIND_OF_LETTER[zone["kind"]],
            code=code,
            name=name[:300],
            folder=f"ENR 5.1-{zone['page']}" if zone.get("page") else "",
            vertical_limits_text=zone["vertical_text"],
            schedule_text=zone["remarks_text"],
            lateral_text=zone["lateral_text"],
            geometry=geometry,
            geometry_method=method if method in GEOMETRY_METHODS else "",
            parse_warnings=warnings,
            review_status=(
                REVIEW_NEEDS_REVIEW
                if zone["review_status"] == aip_parser.REVIEW_NEEDS or ordinal
                else REVIEW_PENDING
            ),
        )
        row.set_bounds()
        rows.append(row)
    return rows


# ── cross-check ─────────────────────────────────────────────────────────────


@dataclass
class CrossRow:
    code: str
    aip_key: str  # source_key of the AIP row ("" when the zone only exists in Google)
    google: object  # AirspaceFeature or None
    result: str
    max_vertex_m: float | None = None
    median_m: float | None = None


def threshold_m():
    value = getattr(settings, "AIRSPACE_CROSSCHECK_THRESHOLD_M", None)
    return float(value) if value not in (None, "") else None


def google_reference():
    """The zones of the current Google snapshot (published, approved, active)."""
    return list(
        AirspaceFeature.objects.filter(
            source_kind=SOURCE_GOOGLE,
            is_active=True,
            review_status=REVIEW_APPROVED,
            snapshot__is_current=True,
            snapshot__status=STATUS_PUBLISHED,
            kind__in=ZONE_KINDS + (AirspaceFeature.KIND_NAVAL,),
        )
    )


def compare(rows, google_features, threshold=None):
    """`CrossRow`s of the AIP zones against the Google zones, matched by zone code.

    Per AIP zone: `missing_in_google` (no zone with that code), or both shapes with the distance of
    every AIP vertex to the Google outline (`max_vertex_m`, `median_m`). Without a threshold the
    result of a measured pair is `measured` (no verdict); with one, `match` or `discrepancy`.
    Per Google zone the AIP does not have: `missing_in_aip` when it has a P/R/D code,
    `google_only` otherwise (the naval zones). A pair that cannot be measured (the AIP gives no
    geometry: arcs and sectors) is `measured` with no distances, never a made-up number.
    """
    by_code = {}
    for feature in google_features:
        if feature.code:
            by_code.setdefault(feature.code, []).append(feature)
    out, used = [], set()
    for row in rows:
        candidates = by_code.get(row.code, []) if row.code else []
        if not candidates:
            out.append(CrossRow(row.code, row.source_key, None, "missing_in_google"))
            continue
        scored = [
            (
                feature,
                vertex_distances_m(row.geometry, feature.geometry)
                if row.has_geometry
                else [],
            )
            for feature in candidates
        ]
        feature, distances = min(
            scored, key=lambda pair: pair[1][-1] if pair[1] else math.inf
        )
        used.add(feature.pk)
        max_m = round(distances[-1], 1) if distances else None
        median = round(statistics.median(distances), 1) if distances else None
        limit = threshold
        if max_m is None or limit is None:
            result = "measured"
        else:
            result = "match" if max_m <= limit else "discrepancy"
        out.append(CrossRow(row.code, row.source_key, feature, result, max_m, median))
    aip_codes = {row.code for row in rows if row.code}
    for feature in google_features:
        if feature.pk in used or feature.code in aip_codes:
            continue
        zone_with_code = feature.kind in ZONE_KINDS and feature.code
        out.append(
            CrossRow(
                feature.code,
                "",
                feature,
                "missing_in_aip" if zone_with_code else "google_only",
            )
        )
    return out


def count_results(cross_rows):
    counts = {}
    for row in cross_rows:
        counts[row.result] = counts.get(row.result, 0) + 1
    return dict(sorted(counts.items()))


# ── sync ────────────────────────────────────────────────────────────────────


@dataclass
class AipReport:
    unchanged: bool = False
    dry_run: bool = False
    parsed: object = None
    total: int = 0
    added: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    archived: list = field(default_factory=list)
    cross: dict = field(default_factory=dict)
    google_missing: bool = False
    superseded: int = 0
    existing: object = None
    snapshot: object = None


def _label(row):
    return row.code or row.name


def attribution_text(amdt, effective):
    date = effective.strftime("%d %b %Y").upper() if effective else "?"
    with translation.override("es"):
        return str(ATTRIBUTION % {"amdt": amdt or "?", "date": date})


def _decided_by_key():
    """Decisions a person already took on a zone, by source key: the current snapshot's, then
    (more recent) those of an unpublished one. A rejected zone counts too."""
    decided = {}
    sources = [
        AirspaceFeature.objects.filter(
            source_kind=SOURCE_AIP_ENR51, is_active=True, snapshot__is_current=True
        ),
        AirspaceFeature.objects.filter(
            source_kind=SOURCE_AIP_ENR51,
            snapshot__status__in=PENDING_STATUSES,
            archived_in__isnull=True,
        ).order_by("snapshot__fetched_at"),
    ]
    for queryset in sources:
        for feature in queryset:
            decided[feature.source_key] = feature
    return decided


def sync_snapshot(parsed, *, source_url="", dry_run=False, now=None):
    """Write the draft snapshot for `parsed` (or report what it would do)."""
    snapshots = AirspaceSnapshot.objects.filter(source_kind=SOURCE_AIP_ENR51)
    latest = snapshots.order_by("-fetched_at").first()
    current = snapshots.filter(is_current=True).first()
    for candidate in (current, latest):
        if candidate and candidate.pdf_sha256 == parsed.sha256:
            return AipReport(
                unchanged=True,
                dry_run=dry_run,
                parsed=parsed,
                total=candidate.feature_count,
                existing=candidate,
            )

    rows = rows_from_zones(parsed.zones)
    published = {
        f.source_key: f
        for f in AirspaceFeature.objects.filter(
            source_kind=SOURCE_AIP_ENR51, is_active=True, snapshot__is_current=True
        )
    }
    decided = _decided_by_key()
    report = AipReport(dry_run=dry_run, parsed=parsed, total=len(rows))
    keys = set()
    for row in rows:
        keys.add(row.source_key)
        old = published.get(row.source_key)
        if old is None:
            report.added.append(_label(row))
        elif old.content_hash != row.content_hash:
            report.changed.append(_label(row))
        else:
            report.kept.append(_label(row))
        before = decided.get(row.source_key)
        if (
            before
            and before.content_hash == row.content_hash
            and before.review_status in (REVIEW_APPROVED, REVIEW_REJECTED)
        ):
            row.carried = True
            row.review_status = before.review_status
            row.reviewed_by_id = before.reviewed_by_id
            row.reviewed_at = before.reviewed_at
            row.geometry = before.geometry
            row.geometry_method = before.geometry_method
            row.set_bounds()
    report.archived = [
        f.code or f.name for key, f in published.items() if key not in keys
    ]

    google = google_reference()
    report.google_missing = not google
    cross = compare(rows, google, threshold_m()) if google else []
    report.cross = count_results(cross)
    if dry_run:
        return report

    moment = now or timezone.now()
    with transaction.atomic():
        snapshot = AirspaceSnapshot.objects.create(
            source_name=SOURCE_NAME,
            source_url=source_url[:500],
            fetched_at=moment,
            sha256=parsed.sha256,
            pdf_sha256=parsed.sha256,
            feature_count=len(rows),
            attribution=attribution_text(parsed.amdt_number, parsed.effective_date),
            added=len(report.added),
            changed=len(report.changed),
            archived=len(report.archived),
            is_current=False,
            source_kind=SOURCE_AIP_ENR51,
            amdt_number=parsed.amdt_number[:20],
            effective_date=parsed.effective_date,
            status=STATUS_DRAFT,
        )
        # An unpublished snapshot that this one replaces is closed, not deleted.
        replaced = snapshots.filter(status__in=PENDING_STATUSES).exclude(pk=snapshot.pk)
        report.superseded = replaced.count()
        AirspaceFeature.objects.filter(snapshot__in=replaced).update(
            archived_in=snapshot, updated_at=moment
        )
        replaced.update(status=STATUS_REJECTED, updated_at=moment)

        created = AirspaceFeature.objects.bulk_create(
            AirspaceFeature(
                snapshot=snapshot,
                source_kind=SOURCE_AIP_ENR51,
                is_active=False,
                source_key=row.source_key,
                content_hash=row.content_hash,
                kind=row.kind,
                code=row.code,
                name=row.name,
                raw_name=row.name[:500],
                folder=row.folder,
                vertical_limits_text=row.vertical_limits_text,
                schedule_text=row.schedule_text,
                lateral_text=row.lateral_text,
                geometry=row.geometry,
                geometry_method=row.geometry_method,
                parse_warnings=row.parse_warnings,
                review_status=row.review_status,
                reviewed_by_id=row.reviewed_by_id,
                reviewed_at=row.reviewed_at,
                min_lat=row.min_lat,
                max_lat=row.max_lat,
                min_lon=row.min_lon,
                max_lon=row.max_lon,
                center_lat=row.center_lat,
                center_lon=row.center_lon,
            )
            for row in rows
        )
        by_key = {feature.source_key: feature for feature in created}
        AirspaceCrossCheck.objects.bulk_create(
            AirspaceCrossCheck(
                snapshot=snapshot,
                code=item.code,
                aip_feature=by_key.get(item.aip_key),
                google_feature=item.google,
                max_vertex_m=item.max_vertex_m,
                median_m=item.median_m,
                result=item.result,
            )
            for item in cross
        )
    report.snapshot = snapshot
    return report
