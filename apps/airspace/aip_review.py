"""LV-361, phase 4: the human review of a draft AIP snapshot, as plain functions.

A zone read from the PDF is a PROPOSAL: a misread coordinate looks as credible as a right one. This
module holds the rules of what a person may do with it (the views only call these):

* **approve** a zone, **reject** it, or **correct** it (vertices or text, validated);
* **approve in bulk** only the CLEAN zones (no warning, with a geometry, still untouched): a zone
  that carries a warning (crossing vertex order, a proposed typo fix, an arc or sector with no
  geometry) is approved one at a time, after looking at it;
* **publish** the snapshot only when EVERY zone is resolved (approved or rejected); that makes it
  the current snapshot of its source, archives the rows of the previous one and leaves the Google
  snapshot alone (the uniqueness is per `source_kind`).

Nothing here draws anything for the end user: `active_aip_features()` is what phase 5 will serve and
it only returns approved zones of the published snapshot.
"""

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import aip_parser
from .kml_import import bounds_of
from .models import (
    REVIEW_APPROVED,
    REVIEW_NEEDS_REVIEW,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    SOURCE_AIP_ENR51,
    STATUS_DRAFT,
    STATUS_IN_REVIEW,
    STATUS_PUBLISHED,
    AirspaceFeature,
    AirspaceSnapshot,
)

REVIEW_PERMISSION = "airspace.review_airspacesnapshot"
PENDING_STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW)
MAX_VERTICES = 500
_DECIMAL_PAIR = re.compile(r"(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)")
MANUAL_EDIT_WARNING = "manual_edit: corrected by a person during the review"

# What each parser warning code means for the reviewer. Unknown codes fall back to the raw code.
WARNING_LABELS = {
    "bowtie": _(
        "The vertex order crosses the polygon: correct the order or reject it."
    ),
    "external_centre": _(
        "Arc centred on a VOR/DME that the text does not give: no geometry."
    ),
    "magnetic_radials": _("Sector defined by magnetic radials: no geometry."),
    "unsupported_shape": _("Shape the parser does not support: no geometry."),
    "vertex_unreadable": _("A vertex could not be read."),
    "incomplete_polygon": _("The polygon is incomplete: it was not proposed."),
    "too_few_vertices": _("Fewer than three usable vertices."),
    "duplicate_vertex": _("Two consecutive vertices are identical."),
    "no_code": _("The source gives this zone no SC code."),
    "no_lateral": _("No lateral limits were found."),
    "no_coordinates": _("No coordinates were found in the lateral limits."),
    "circle_centre": _("The circle does not have exactly one centre."),
    "radius_missing": _("No radius with a recognised unit."),
    "radius_invalid": _("The radius is not a positive number."),
    "radius_implausible": _("The radius looks implausibly large."),
    "radius_discrepancy": _("The two radius values of the source disagree."),
    "unit_capital_m": _("The unit M was read as metres."),
    "space_in_decimal": _("A stray space inside a decimal was joined (source typo)."),
    "space_before_hemisphere": _("A space before the hemisphere letter was ignored."),
    "six_digit_longitude": _(
        "A six-digit longitude was read as degrees, minutes, seconds."
    ),
    "misplaced_space": _("A misplaced space was moved (source typo)."),
    "separator_typo": _("A separator was read as degrees and minutes (source typo)."),
    "duplicate_zone": _("The same zone appears more than once in the PDF."),
    "manual_edit": _("Corrected by a person during the review."),
}


def warning_items(feature):
    """[(label, detail)] for the warnings of a zone: the translated meaning and the parser's note."""
    items = []
    for warning in feature.parse_warnings or []:
        code, _sep, detail = str(warning).partition(": ")
        items.append((WARNING_LABELS.get(code, code), detail))
    return items


# ── state of a zone ─────────────────────────────────────────────────────────


def has_geometry(feature):
    return bool((feature.geometry or {}).get("coordinates"))


def is_flagged(feature):
    """A zone a person must look at on its own: a warning, no geometry, or already sent back."""
    return (
        bool(feature.parse_warnings)
        or not has_geometry(feature)
        or feature.review_status == REVIEW_NEEDS_REVIEW
    )


def is_resolved(feature):
    return feature.review_status in (REVIEW_APPROVED, REVIEW_REJECTED)


def ring_of(feature):
    """The outer ring (without the closing vertex) as [(lon, lat)], or []."""
    if (feature.geometry or {}).get("type") != "Polygon":
        return []
    ring = feature.geometry["coordinates"][0]
    return [tuple(p) for p in ring[:-1]]


def crosses_itself(feature):
    return aip_parser.ring_self_intersects(ring_of(feature))


def zones_of(snapshot):
    return AirspaceFeature.objects.filter(snapshot=snapshot).order_by("code", "name")


def counts(snapshot):
    zones = list(zones_of(snapshot))
    return {
        "total": len(zones),
        "approved": sum(f.review_status == REVIEW_APPROVED for f in zones),
        "rejected": sum(f.review_status == REVIEW_REJECTED for f in zones),
        "unresolved": sum(not is_resolved(f) for f in zones),
        "flagged_unresolved": sum(is_flagged(f) and not is_resolved(f) for f in zones),
        "bulk": sum(is_bulk_candidate(f) for f in zones),
    }


def is_bulk_candidate(feature):
    return feature.review_status == REVIEW_PENDING and not is_flagged(feature)


def bulk_candidates(snapshot):
    return [f for f in zones_of(snapshot) if is_bulk_candidate(f)]


def _check_open(snapshot):
    if (
        snapshot.source_kind != SOURCE_AIP_ENR51
        or snapshot.status not in PENDING_STATUSES
    ):
        raise ValidationError(_("This snapshot is no longer open for review."))


def _touch(snapshot):
    if snapshot.status == STATUS_DRAFT:
        snapshot.status = STATUS_IN_REVIEW
        snapshot.save(update_fields=["status", "updated_at"])


# ── vertices ────────────────────────────────────────────────────────────────


def parse_vertices(text):
    """[(lon, lat)] from lines of `lat, lon` (decimal degrees or DMS), validated.

    Raises `ValidationError` with a message the person can act on: the line, what is wrong, what
    range is expected. A closing vertex equal to the first is dropped. The ring must be simple.
    """
    vertices = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) > MAX_VERTICES:
        raise ValidationError(
            _("At most %(max)s vertices are accepted."), params={"max": MAX_VERTICES}
        )
    for number, line in enumerate(lines, 1):
        lat, lon = _read_pair(line, number)
        if not aip_parser.LAT_RANGE[0] <= lat <= aip_parser.LAT_RANGE[1]:
            raise ValidationError(
                _("Line %(n)s: latitude %(v)s is outside %(lo)s to %(hi)s."),
                params={
                    "n": number,
                    "v": lat,
                    "lo": aip_parser.LAT_RANGE[0],
                    "hi": aip_parser.LAT_RANGE[1],
                },
            )
        if not aip_parser.LON_RANGE[0] <= lon <= aip_parser.LON_RANGE[1]:
            raise ValidationError(
                _("Line %(n)s: longitude %(v)s is outside %(lo)s to %(hi)s."),
                params={
                    "n": number,
                    "v": lon,
                    "lo": aip_parser.LON_RANGE[0],
                    "hi": aip_parser.LON_RANGE[1],
                },
            )
        vertices.append((round(lon, 6), round(lat, 6)))
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices.pop()
    if len(set(vertices)) < 3:
        raise ValidationError(_("A polygon needs at least three different vertices."))
    if any(a == b for a, b in zip(vertices, vertices[1:])):
        raise ValidationError(_("Two consecutive vertices are identical."))
    if aip_parser.ring_self_intersects(vertices):
        raise ValidationError(
            _(
                "The polygon crosses itself: put the vertices in order around the outline."
            )
        )
    return vertices


def _read_pair(line, number):
    decimal = _DECIMAL_PAIR.fullmatch(line)
    if decimal:
        return float(decimal.group(1)), float(decimal.group(2))
    try:
        coordinate = aip_parser.parse_coordinate(line)
    except aip_parser.CoordinateError as exc:
        raise ValidationError(
            _(
                "Line %(n)s is not a coordinate: use «lat, lon» in decimal degrees "
                "(for example -33.4569, -70.6483) or degrees, minutes and seconds."
            ),
            params={"n": number},
        ) from exc
    return coordinate.lat, coordinate.lon


def polygon_geometry(vertices):
    ring = [[lon, lat] for lon, lat in vertices]
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def vertices_text(feature):
    """The outer ring as editable text, one `lat, lon` per line."""
    return "\n".join(f"{lat:.6f}, {lon:.6f}" for lon, lat in ring_of(feature))


# ── actions ─────────────────────────────────────────────────────────────────


def approve(feature, user, now=None):
    """Approve one zone. A polygon that crosses itself cannot be approved: fix its order first."""
    snapshot = feature.snapshot
    _check_open(snapshot)
    if has_geometry(feature) and crosses_itself(feature):
        raise ValidationError(
            _(
                "The polygon of %(code)s crosses itself: correct the vertex order before approving."
            )
            % {"code": feature.code or feature.name}
        )
    with transaction.atomic():
        feature.review_status = REVIEW_APPROVED
        feature.reviewed_by = user
        feature.reviewed_at = now or timezone.now()
        feature.save(
            update_fields=["review_status", "reviewed_by", "reviewed_at", "updated_at"]
        )
        _touch(snapshot)
    return feature


def reject(feature, user, now=None):
    snapshot = feature.snapshot
    _check_open(snapshot)
    with transaction.atomic():
        feature.review_status = REVIEW_REJECTED
        feature.reviewed_by = user
        feature.reviewed_at = now or timezone.now()
        feature.save(
            update_fields=["review_status", "reviewed_by", "reviewed_at", "updated_at"]
        )
        _touch(snapshot)
    return feature


def correct(feature, user, *, vertices=None, texts=None, now=None):
    """Apply a person's correction and send the zone back to be approved again, on its own.

    `vertices` is the output of `parse_vertices`; `texts` a dict of the editable texts. Every text
    goes through the contact scrubber again: a person typing is not a reason to store a phone. The
    `content_hash` is NOT touched: it identifies what the SOURCE said, so a later import of the
    same text can keep this correction.
    """
    snapshot = feature.snapshot
    _check_open(snapshot)
    changed = []
    with transaction.atomic():
        if vertices is not None:
            feature.geometry = polygon_geometry(vertices)
            feature.geometry_method = "polygon"
            bounds = bounds_of(feature.geometry)
            feature.min_lat, feature.max_lat, feature.min_lon, feature.max_lon = bounds
            feature.center_lat = round((bounds[0] + bounds[1]) / 2, 6)
            feature.center_lon = round((bounds[2] + bounds[3]) / 2, 6)
            changed.append("geometry")
        for field, value in (texts or {}).items():
            clean = aip_parser.scrub_contacts(value or "")
            if clean != getattr(feature, field):
                setattr(feature, field, clean)
                changed.append(field)
        if not changed:
            return feature, []
        if MANUAL_EDIT_WARNING not in (feature.parse_warnings or []):
            feature.parse_warnings = [
                *(feature.parse_warnings or []),
                MANUAL_EDIT_WARNING,
            ]
        feature.review_status = REVIEW_NEEDS_REVIEW
        feature.reviewed_by = None
        feature.reviewed_at = None
        feature.save()
        _touch(snapshot)
    return feature, changed


def approve_clean_in_bulk(snapshot, user, now=None):
    """Approve every clean, untouched zone at once. Returns the approved zones."""
    _check_open(snapshot)
    moment = now or timezone.now()
    approved = []
    with transaction.atomic():
        for feature in bulk_candidates(snapshot):
            if has_geometry(feature) and crosses_itself(feature):
                continue
            feature.review_status = REVIEW_APPROVED
            feature.reviewed_by = user
            feature.reviewed_at = moment
            feature.save(
                update_fields=[
                    "review_status",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )
            approved.append(feature)
        if approved:
            _touch(snapshot)
    return approved


# ── publishing ──────────────────────────────────────────────────────────────


def publish_blockers(snapshot):
    """Why the snapshot cannot be published yet, as translated messages (empty: it can)."""
    blockers = []
    if (
        snapshot.source_kind != SOURCE_AIP_ENR51
        or snapshot.status not in PENDING_STATUSES
    ):
        return [_("This snapshot is no longer open for review.")]
    state = counts(snapshot)
    if state["unresolved"]:
        blockers.append(
            _(
                "%(n)s zone(s) are still unresolved: approve, correct or reject each one."
            )
            % {"n": state["unresolved"]}
        )
    if not state["approved"]:
        blockers.append(_("There is no approved zone to publish."))
    return blockers


def publish(snapshot, user, now=None):
    """Make the snapshot the current one of its source, in one transaction.

    The previous current snapshot of the SAME source stops being current and its rows are archived
    (`archived_in` = this snapshot); the rows of this one become active. The Google snapshot is not
    touched. Raises `ValidationError` with every reason when something is still unresolved.
    """
    moment = now or timezone.now()
    with transaction.atomic():
        snapshot = AirspaceSnapshot.objects.get(pk=snapshot.pk)
        blockers = publish_blockers(snapshot)
        if blockers:
            raise ValidationError(blockers)
        previous = AirspaceSnapshot.objects.filter(
            source_kind=snapshot.source_kind, is_current=True
        ).exclude(pk=snapshot.pk)
        AirspaceFeature.objects.filter(snapshot__in=previous, is_active=True).update(
            is_active=False, archived_in=snapshot, updated_at=moment
        )
        previous.update(is_current=False, updated_at=moment)
        AirspaceFeature.objects.filter(snapshot=snapshot).update(
            is_active=True, updated_at=moment
        )
        snapshot.status = STATUS_PUBLISHED
        snapshot.is_current = True
        snapshot.save(update_fields=["status", "is_current", "updated_at"])
    return snapshot


def active_aip_features():
    """What phase 5 will serve: approved zones of the published, current AIP snapshot."""
    return AirspaceFeature.objects.filter(
        is_active=True,
        source_kind=SOURCE_AIP_ENR51,
        review_status=REVIEW_APPROVED,
        snapshot__is_current=True,
        snapshot__status=STATUS_PUBLISHED,
    )
