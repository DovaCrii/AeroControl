"""Parser for the AIP-Chile ENR 5.1 table (prohibited, restricted and dangerous areas).

LV-361, phase 2. Pure functions: no ORM, no network, no file access. The PDF
layer (`aip_pdf.py`) hands in words with their bounding box; everything else
here works on text.

Principles (see docs of LV-361):
- A misread coordinate looks as credible as a right one, so **nothing is fixed
  silently**. Known typos come back as a proposed value *plus* a warning; what
  cannot be decided is an error and the vertex is left out of the geometry.
- A polygon whose vertex ORDER crosses itself is flagged, never reordered.
- Arcs and radial sectors depend on a VOR/DME centre that is not in the text:
  they come back without geometry. A person loads the centre, never the parser.
- Vertical limits and schedules stay as the source wrote them (no conversion).
- Remarks carry names, phones and e-mails of officials. They are scrubbed here,
  before any other layer sees them.

Warnings are strings `"<code>: <message>"`; `warning_codes()` lists the codes.
"""

import datetime
import math
import re
from dataclasses import dataclass, field

from .kml_import import normalize_zone_code

LAT_RANGE = (-57.0, -17.0)
LON_RANGE = (-110.0, -66.0)
NM_IN_M = 1852.0
CIRCLE_SEGMENTS = 72
CONTACT_PLACEHOLDER = "[contacto omitido]"

REVIEW_CLEAN = "clean"
REVIEW_NEEDS = "needs_review"


class CoordinateError(ValueError):
    """The text is not a coordinate, or is ambiguous / out of range."""


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float
    warnings: tuple = ()
    raw: str = ""


@dataclass(frozen=True)
class CoordinateMatch:
    start: int
    end: int
    raw: str
    coordinate: Coordinate | None = None
    error: str = ""


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------

_PAIR = re.compile(
    r"""
    (?<![\w.,])
    (?P<lat>\d[\d .,]*?)(?P<lsp>\s*)(?P<ns>[NS])(?![A-Za-z])
    \s*[/–—-]?\s*
    (?P<lon>\d[\d .,]*?)(?P<osp>\s*)(?P<ew>[EW])(?![A-Za-z])
    """,
    re.VERBOSE,
)


def _warn(code, message):
    return f"{code}: {message}"


def warning_codes(warnings):
    """The codes of a list of warnings, in order."""
    return [w.split(":", 1)[0] for w in warnings]


def _to_float(text):
    return float(text.replace(",", "."))


def _parse_angle(raw, *, is_lon, space_before_hemisphere):
    """(degrees, minutes, seconds, warnings) for one half of a pair, or CoordinateError."""
    warnings = []
    text = raw.strip()
    fixed = re.sub(r"(\d)\s+([.,]\d)|(\d[.,])\s+(\d)", r"\1\2\3\4", text)
    if fixed != text:
        warnings.append(
            _warn(
                "space_in_decimal", f"stray space inside a decimal ({text!r}); joined"
            )
        )
    tokens = fixed.split()
    deg_digits = (2, 3) if is_lon else (2,)

    if len(tokens) == 1:
        match = re.fullmatch(r"(\d+)(?:([.,])(\d+))?", tokens[0])
        if not match:
            raise CoordinateError(f"unrecognised angle {text!r}")
        whole, _, frac = match.groups()
        frac = frac or ""
        if is_lon and len(whole) == 6:
            warnings.append(
                _warn(
                    "six_digit_longitude",
                    f"longitude {text!r} has six digits; read as DDMMSS",
                )
            )
            d, m, s = whole[:2], whole[2:4], whole[4:] + ("." + frac if frac else "")
        elif (is_lon and len(whole) == 7) or (not is_lon and len(whole) == 6):
            cut = 3 if is_lon else 2
            d, m, s = (
                whole[:cut],
                whole[cut : cut + 2],
                whole[cut + 2 :] + ("." + frac if frac else ""),
            )
        else:
            raise CoordinateError(f"ambiguous compact angle {text!r}")
        if space_before_hemisphere and frac:
            warnings.append(
                _warn(
                    "space_before_hemisphere",
                    f"space before the hemisphere in {text!r}",
                )
            )
    elif len(tokens) == 2 and re.fullmatch(r"\d{2,3}[.,]\d{2}", tokens[0]):
        if not re.fullmatch(r"\d{2}(?:[.,]\d+)?", tokens[1]):
            raise CoordinateError(f"unrecognised angle {text!r}")
        d, m = re.split(r"[.,]", tokens[0])
        s = tokens[1]
        warnings.append(
            _warn(
                "separator_typo",
                f"{tokens[0]!r} read as degrees and minutes ({d} {m}); check the source",
            )
        )
    elif len(tokens) == 3:
        d, m, s = tokens
        if (
            is_lon
            and len(d) == 2
            and len(m) == 3
            and m.startswith("0")
            and re.fullmatch(r"\d{2}", s)
        ):
            joined = d + m + s
            d, m, s = joined[:3], joined[3:5], joined[5:]
            warnings.append(
                _warn(
                    "misplaced_space", f"{text!r} read as {d} {m} {s}; check the source"
                )
            )
    else:
        raise CoordinateError(f"unrecognised angle {text!r}")

    if not re.fullmatch(r"\d{2,3}", d) or len(d) not in deg_digits:
        raise CoordinateError(
            f"degrees {d!r} do not fit {'a longitude' if is_lon else 'a latitude'}"
        )
    if not re.fullmatch(r"\d{2}", m):
        raise CoordinateError(f"minutes {m!r} are not two digits")
    if not re.fullmatch(r"\d{1,2}(?:[.,]\d+)?", s):
        raise CoordinateError(f"seconds {s!r} are not valid")
    degrees, minutes, seconds = int(d), int(m), _to_float(s)
    if minutes >= 60 or seconds >= 60:
        raise CoordinateError(f"minutes/seconds out of range in {text!r}")
    return degrees + minutes / 60 + seconds / 3600, warnings


def _build(match):
    raw = match.group(0)
    lat_abs, w1 = _parse_angle(
        match.group("lat"),
        is_lon=False,
        space_before_hemisphere=bool(match.group("lsp")),
    )
    lon_abs, w2 = _parse_angle(
        match.group("lon"),
        is_lon=True,
        space_before_hemisphere=bool(match.group("osp")),
    )
    lat = -lat_abs if match.group("ns") == "S" else lat_abs
    lon = -lon_abs if match.group("ew") == "W" else lon_abs
    if not LAT_RANGE[0] <= lat <= LAT_RANGE[1]:
        raise CoordinateError(f"latitude {lat:.4f} outside {LAT_RANGE}")
    if not LON_RANGE[0] <= lon <= LON_RANGE[1]:
        raise CoordinateError(f"longitude {lon:.4f} outside {LON_RANGE}")
    return Coordinate(round(lat, 6), round(lon, 6), tuple(w1 + w2), raw)


def find_coordinates(text):
    """Every lat/lon pair in `text`, in order. An unreadable pair carries `.error`."""
    found = []
    for match in _PAIR.finditer(text):
        raw = match.group(0)
        try:
            found.append(
                CoordinateMatch(match.start(), match.end(), raw, _build(match))
            )
        except CoordinateError as exc:
            found.append(
                CoordinateMatch(match.start(), match.end(), raw, None, str(exc))
            )
    return found


def parse_coordinate(text):
    """One `Coordinate` from a string holding exactly one pair, or CoordinateError."""
    matches = find_coordinates(text)
    if len(matches) != 1 or text.strip() != matches[0].raw.strip():
        raise CoordinateError(f"expected exactly one coordinate pair in {text!r}")
    if matches[0].error:
        raise CoordinateError(matches[0].error)
    return matches[0].coordinate


# --------------------------------------------------------------------------
# Personal data
# --------------------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_PHONE_INTL = re.compile(r"(?<![\w])\+\d[\d\s().\-]{6,}\d")
_PHONE_AREA = re.compile(r"\(\+?\d{1,4}[\s\-]?\d{0,3}\)[\s\-]?\d[\d\s\-]{5,}\d")
_PHONE_LABEL = re.compile(
    r"(?i)\b(fono|fonos|tel|tels|telf|telefono|tel[eé]fono|telefonos|tel[eé]fonos|cel|celular|"
    r"phone|fax|anexo|ph)\b\.?\s*[:\-]?\s*\+?\d[\d\s().\-/]*\d"
)
_PHONE_BARE = re.compile(
    r"(?<![\w.,/+\-])(?:\d(?:[ \-]?\d){8,}(?!\w|[.,]\d)|\d{7,8}(?!\w|-|[.,]\d))"
)
_TITLED_NAME = re.compile(
    r"\b(?:Sr\.?|Sra\.?|Srta\.?|Cte\.?|Cdte\.?|Cmdte\.?|Cap\.?|Capit[aá]n|Mayor|Teniente|Tte\.?|"
    r"Cnel\.?|Coronel|Gral\.?|General|Sargento|Sgto\.?|Don|Do[nñ]a)\s+"
    r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+|\b)){1,3}"
)


def scrub_contacts(text):
    """`text` with phones, e-mails and titled names replaced by a placeholder.

    Heuristic, deliberately greedy on contact-looking shapes and careful not to
    eat schedules ("0800-1700"), frequencies ("118.100") or flight levels. A
    free-form name without title cannot be recognised; the remarks are never
    shown or stored as source text without this pass.
    """
    out = _EMAIL.sub(CONTACT_PLACEHOLDER, text)
    out = _PHONE_INTL.sub(CONTACT_PLACEHOLDER, out)
    out = _PHONE_AREA.sub(CONTACT_PLACEHOLDER, out)

    def keep_label(match):
        label = re.match(r"(?i)\b\w+\b\.?\s*[:\-]?\s*", match.group(0)).group(0)
        return label + CONTACT_PLACEHOLDER

    out = _PHONE_LABEL.sub(keep_label, out)
    out = _PHONE_BARE.sub(CONTACT_PLACEHOLDER, out)
    out = _TITLED_NAME.sub(CONTACT_PLACEHOLDER + " ", out)
    out = re.sub(
        r"(?:\[contacto omitido\][\s,;/y]*){2,}", CONTACT_PLACEHOLDER + " ", out
    )
    return re.sub(r"\s+", " ", out).strip()


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def _orient(a, b, c):
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)


def _on_segment(a, b, c):
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[
        1
    ] <= max(a[1], b[1])


def _segments_touch(p1, p2, p3, p4):
    o1, o2, o3, o4 = (
        _orient(p1, p2, p3),
        _orient(p1, p2, p4),
        _orient(p3, p4, p1),
        _orient(p3, p4, p2),
    )
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(p1, p2, p3))
        or (o2 == 0 and _on_segment(p1, p2, p4))
        or (o3 == 0 and _on_segment(p3, p4, p1))
        or (o4 == 0 and _on_segment(p3, p4, p2))
    )


def ring_self_intersects(vertices):
    """True when the closed ring of (lon, lat) vertices crosses or touches itself.

    Adjacent edges only count when one doubles back over the other (a spike).
    """
    n = len(vertices)
    if n < 3:
        return False
    edges = [(vertices[i], vertices[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            (a, b), (c, d) = edges[i], edges[j]
            adjacent = j == i + 1 or (i == 0 and j == n - 1)
            if adjacent:
                shared = b if j == i + 1 else a
                other_i, other_j = (a, d) if j == i + 1 else (b, c)
                if _orient(other_i, shared, other_j) == 0:
                    v1 = (other_i[0] - shared[0], other_i[1] - shared[1])
                    v2 = (other_j[0] - shared[0], other_j[1] - shared[1])
                    if v1[0] * v2[0] + v1[1] * v2[1] > 0:
                        return True
                continue
            if _segments_touch(a, b, c, d):
                return True
    return False


def circle_ring(lat, lon, radius_m, segments=CIRCLE_SEGMENTS):
    """Closed ring of [lon, lat] points on a sphere around a centre."""
    earth = 6371008.8
    phi1, lam1, delta = math.radians(lat), math.radians(lon), radius_m / earth
    ring = []
    for step in range(segments):
        theta = 2 * math.pi * step / segments
        phi2 = math.asin(
            math.sin(phi1) * math.cos(delta)
            + math.cos(phi1) * math.sin(delta) * math.cos(theta)
        )
        lam2 = lam1 + math.atan2(
            math.sin(theta) * math.sin(delta) * math.cos(phi1),
            math.cos(delta) - math.sin(phi1) * math.sin(phi2),
        )
        ring.append([round(math.degrees(lam2), 6), round(math.degrees(phi2), 6)])
    ring.append(list(ring[0]))
    return ring


_UNIT_FACTOR = {"nm": NM_IN_M, "km": 1000.0, "m": 1.0}
_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"(NM|nm|Nm|km|KM|Km|m|M)(?![A-Za-z])"
_RADIUS_PATTERNS = (
    re.compile(
        rf"{_NUM}\s*{_UNIT}\s*(?:\(\s*{_NUM}\s*{_UNIT}\s*\))?\s*(?:de\s+)?radio", re.I
    ),
    re.compile(rf"radio\s*(?:de\s+)?{_NUM}\s*{_UNIT}", re.I),
    re.compile(rf"radius\s*(?:of\s+)?{_NUM}\s*{_UNIT}", re.I),
    re.compile(rf"{_NUM}\s*{_UNIT}\s*radius", re.I),
    re.compile(rf"radio\s+centrado\s+en\s*:?\s*{_NUM}\s*{_UNIT}", re.I),
)


def _meters(number, unit):
    key = "nm" if unit.lower() == "nm" else ("km" if unit.lower() == "km" else "m")
    return _to_float(number) * _UNIT_FACTOR[key], key


def parse_radius(text):
    """(radius_m, warnings) from the first radius statement in `text`, or (None, warnings).

    Units: NM, km, m. A capital `M` alone is read as metres (the AIP writes both
    "500m" and "500M") and flagged. "500m (0.3 NM)" keeps the first value and
    warns when the two disagree by more than 5 %.
    """
    for pattern in _RADIUS_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        warnings = []
        number, unit = groups[0], groups[1]
        radius, _ = _meters(number, unit)
        if unit == "M":
            warnings.append(
                _warn(
                    "unit_capital_m", f"unit 'M' in {match.group(0)!r} read as metres"
                )
            )
        if len(groups) >= 4 and groups[2] and groups[3]:
            other, _ = _meters(groups[2], groups[3])
            if abs(other - radius) / max(other, radius) > 0.05:
                warnings.append(
                    _warn(
                        "radius_discrepancy",
                        f"{match.group(0)!r}: {radius:.0f} m vs {other:.0f} m; kept the first",
                    )
                )
        if radius <= 0:
            return None, [
                _warn("radius_invalid", f"radius {match.group(0)!r} is not positive")
            ]
        if radius > 100 * NM_IN_M:
            warnings.append(
                _warn("radius_implausible", f"radius {radius:.0f} m is above 100 NM")
            )
        return radius, warnings
    return None, [
        _warn("radius_missing", "no radius with a recognised unit (NM, km, m)")
    ]


# --------------------------------------------------------------------------
# Zone blocks
# --------------------------------------------------------------------------

_START_CODE = re.compile(r"^\s*SC\s*[-–—]?\s*[PRD]\s*[-–—]?\s*\d{1,3}\s+FIR\b", re.I)
_START_NO_CODE = re.compile(
    r"^\s*ZONA\s+(PROHIBIDA|RESTRINGIDA|PELIGROSA)\s*[-–—]\s*FIR\b", re.I
)
_FIR = re.compile(r"\bFIR\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]*?)(?:\s*[-–—]\s*(\S.*))?$")
_KIND_WORD = {"PROHIBIDA": "P", "RESTRINGIDA": "R", "PELIGROSA": "D"}
_LATERAL_START = re.compile(
    r"(?i)^(l[ií]mites?\s+laterales|[aá]rea\s+definida|espacio\s+a[eé]reo|c[ií]rculo|circle|radio\b|"
    r"cuadril[aá]tero|siguiendo|entre\s+los\s+radiales)"
)
_FURNITURE = re.compile(
    r"(AIP-CHILE|AIS ?- ?CHILE|AMDT NR \d+|ENR 5\.1-\d+|\bVOLUMEN? I\b|"
    r"^ZONAS\s+(PELIGROSAS|PROHIBIDAS|RESTRINGIDAS)|\b(DANGEROUS|PROHIBITED|RESTRICTED) AREAS\b)"
)


def split_blocks_by_code(lines):
    """Indices where a zone starts in a list of column-1 lines (`SC-P3 FIR ...`)."""
    return [
        i
        for i, line in enumerate(lines)
        if _START_CODE.match(line) or _START_NO_CODE.match(line)
    ]


def _as_lines(value):
    if isinstance(value, str):
        value = value.splitlines()
    return [
        re.sub(r"\s+", " ", line).strip() for line in value if line and line.strip()
    ]


def _header(line):
    """(code, kind, fir, name_start) from the first line of a block."""
    code = ""
    kind = ""
    if _START_CODE.match(line):
        code = normalize_zone_code(line)
        kind = code[3] if code else ""
    else:
        word = _START_NO_CODE.match(line).group(1).upper()
        kind = _KIND_WORD[word]
    fir, name_start = "", ""
    match = _FIR.search(line)
    if match:
        fir = match.group(1).strip()
        name_start = (match.group(2) or "").strip()
    return code, kind, fir, name_start


def _classify(lateral):
    low = lateral.lower()
    if re.search(r"\bradiales?\b", low):
        return "sector"
    if re.search(r"\barco\b|\barc\b", low):
        return "arc"
    if re.search(r"cuadril[aá]tero", low):
        return "unsupported"
    if re.search(r"c[ií]rculo|\bcircle\b|\bradio\b|\bradius\b", low):
        return "circle"
    return "polygon"


def _polygon(matches, warnings, params):
    vertices = []
    unreadable = 0
    for index, match in enumerate(matches, 1):
        if match.error:
            unreadable += 1
            warnings.append(
                _warn(
                    "vertex_unreadable",
                    f"vertex {index} ({match.raw.strip()!r}): {match.error}",
                )
            )
            continue
        for w in match.coordinate.warnings:
            code, message = w.split(": ", 1)
            warnings.append(f"{code}: vertex {index}: {message}")
        vertices.append((match.coordinate.lon, match.coordinate.lat))
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices.pop()
    params["vertices_ok"] = len(vertices)
    if unreadable:
        warnings.append(
            _warn(
                "incomplete_polygon",
                f"{unreadable} vertex(es) unreadable; polygon not proposed",
            )
        )
        return None
    if len(set(vertices)) < 3:
        warnings.append(
            _warn(
                "too_few_vertices",
                f"{len(vertices)} usable vertices; a polygon needs three",
            )
        )
        return None
    if any(a == b for a, b in zip(vertices, vertices[1:])):
        warnings.append(
            _warn("duplicate_vertex", "two consecutive vertices are identical")
        )
    if ring_self_intersects(vertices):
        warnings.append(
            _warn(
                "bowtie",
                "the vertex order crosses the polygon; kept as written, not reordered. Review against the chart",
            )
        )
    ring = [[lon, lat] for lon, lat in vertices]
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def parse_zone(col1, col2="", col3=""):
    """One zone from its three columns (strings or lists of lines)."""
    lines = _as_lines(col1)
    if not lines or not (_START_CODE.match(lines[0]) or _START_NO_CODE.match(lines[0])):
        raise ValueError(
            "column 1 must start with the zone header line (SC-xx FIR ...)"
        )
    code, kind, fir, name_start = _header(lines[0])
    rest = lines[1:]
    lateral_at = len(rest)
    for i, line in enumerate(rest):
        if _LATERAL_START.match(line) or find_coordinates(line):
            lateral_at = i
            break
    name_lines = ([name_start] if name_start else []) + rest[:lateral_at]
    lateral = " ".join(rest[lateral_at:])
    warnings = []
    params = {}
    geometry = None
    method = "none"

    if not code:
        warnings.append(_warn("no_code", "the source gives this zone no SC code"))
    if not lateral:
        warnings.append(_warn("no_lateral", "no lateral limits found in column 1"))
    else:
        method = _classify(lateral)
        matches = find_coordinates(lateral)
        params["vertices_found"] = len(matches)
        if method == "sector":
            warnings.append(
                _warn(
                    "magnetic_radials",
                    "sector defined by magnetic radials from a VOR/DME; no geometry",
                )
            )
        elif method == "arc":
            warnings.append(
                _warn(
                    "external_centre",
                    "arc centred on a VOR/DME not given in the text; no geometry",
                )
            )
        elif method == "unsupported":
            warnings.append(
                _warn(
                    "unsupported_shape",
                    "shape not supported (rectangle/quadrilateral); no geometry",
                )
            )
        elif method == "circle":
            radius, radius_warnings = parse_radius(lateral)
            warnings.extend(radius_warnings)
            params["radius_m"] = radius
            good = [m for m in matches if not m.error]
            if len(matches) != 1:
                warnings.append(
                    _warn(
                        "circle_centre",
                        f"{len(matches)} coordinate pairs found; one centre expected",
                    )
                )
            elif not good:
                warnings.append(
                    _warn(
                        "vertex_unreadable",
                        f"centre {matches[0].raw.strip()!r}: {matches[0].error}",
                    )
                )
            elif radius:
                centre = good[0].coordinate
                for w in centre.warnings:
                    warnings.append(w)
                params.update(centre_lat=centre.lat, centre_lon=centre.lon)
                geometry = {
                    "type": "Polygon",
                    "coordinates": [circle_ring(centre.lat, centre.lon, radius)],
                }
        else:
            if not matches:
                method = "none"
                warnings.append(
                    _warn(
                        "no_coordinates", "no coordinates found in the lateral limits"
                    )
                )
            else:
                geometry = _polygon(matches, warnings, params)

    vertical = " / ".join(_as_lines(col2))
    remarks = " ".join(_as_lines(col3))
    zone = {
        "code": code,
        "kind": kind,
        "name": scrub_contacts(" / ".join(name_lines)),
        "fir": fir,
        "lateral_text": scrub_contacts(lateral),
        "vertical_text": scrub_contacts(vertical),
        "remarks_text": scrub_contacts(remarks),
        "geometry": geometry,
        "geometry_method": method,
        "params": params,
        "warnings": warnings,
    }
    zone["review_status"] = (
        REVIEW_NEEDS if warnings or geometry is None else REVIEW_CLEAN
    )
    return zone


def summarize(zones):
    """Coverage numbers for a parse (no text from the source)."""
    by_kind, by_method, codes = {}, {}, {}
    vertices_found = vertices_ok = 0
    for zone in zones:
        by_kind[zone["kind"] or "?"] = by_kind.get(zone["kind"] or "?", 0) + 1
        by_method[zone["geometry_method"]] = (
            by_method.get(zone["geometry_method"], 0) + 1
        )
        vertices_found += (
            zone["params"].get("vertices_found", 0)
            if zone["geometry_method"] == "polygon"
            else 0
        )
        vertices_ok += (
            zone["params"].get("vertices_ok", 0)
            if zone["geometry_method"] == "polygon"
            else 0
        )
        for code in warning_codes(zone["warnings"]):
            codes[code] = codes.get(code, 0) + 1
    return {
        "zones": len(zones),
        "by_kind": by_kind,
        "by_method": by_method,
        "with_geometry": sum(1 for z in zones if z["geometry"]),
        "clean": sum(1 for z in zones if z["review_status"] == REVIEW_CLEAN),
        "needs_review": sum(1 for z in zones if z["review_status"] == REVIEW_NEEDS),
        "without_code": sum(1 for z in zones if not z["code"]),
        "polygon_vertices_found": vertices_found,
        "polygon_vertices_ok": vertices_ok,
        "warning_codes": dict(sorted(codes.items())),
    }


# --------------------------------------------------------------------------
# Words with bounding boxes -> blocks
# --------------------------------------------------------------------------

LINE_TOLERANCE = 2.5


@dataclass
class RawBlock:
    col1: list = field(default_factory=list)
    col2: list = field(default_factory=list)
    col3: list = field(default_factory=list)
    page: int = 0  # 1-based page of the code line (the printed page is ENR 5.1-<page>)


def _lines_of(words):
    """[(top, text)] grouping words that share a baseline, left to right."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and word["top"] - lines[-1][0] <= LINE_TOLERANCE:
            lines[-1][1].append(word)
        else:
            lines.append((word["top"], [word]))
    return [
        (top, " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])))
        for top, ws in lines
    ]


_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")


def _clean_words(words):
    """Words without the private-use bullet glyphs Word leaves before some lines."""
    cleaned = []
    for word in words:
        text = _PRIVATE_USE.sub("", word["text"])
        if text.strip():
            cleaned.append({**word, "text": text})
    return cleaned


def column_bounds(words):
    """(x between columns 1|2, x between 2|3) from the header row «1 2 3», or None."""
    for top, text in _lines_of(words):
        if text.split() == ["1", "2", "3"]:
            row = sorted(
                (w for w in words if abs(w["top"] - top) <= LINE_TOLERANCE),
                key=lambda w: w["x0"],
            )
            centres = [(w["x0"] + w["x1"]) / 2 for w in row]
            return (centres[0] + centres[1]) / 2, (centres[1] + centres[2]) / 2, top
    return None


def blocks_from_words(pages):
    """Zone blocks from pages of words ({text, x0, x1, top, bottom}); columns by x position.

    The column limits come from the «1 2 3» row of each page (pages without it
    reuse the previous page's). Everything above that row and the page
    furniture is dropped. Columns 2 and 3 attach to the block whose code line
    is the last one above them, across page breaks.
    """
    bounds = None
    entries = []  # (page, top, column, text)
    for page_index, words in enumerate(pages):
        words = _clean_words(words)
        found = column_bounds(words)
        header_top = None
        if found:
            bounds, header_top = found[:2], found[2]
        if bounds is None:
            continue
        drop = set()
        for top, text in _lines_of(words):
            if (
                header_top is not None and top <= header_top + LINE_TOLERANCE
            ) or _FURNITURE.search(text):
                drop.add(top)
        kept = [
            w
            for w in words
            if not any(abs(w["top"] - t) <= LINE_TOLERANCE for t in drop)
        ]
        columns = ([], [], [])
        for word in kept:
            columns[
                0 if word["x0"] < bounds[0] else (1 if word["x0"] < bounds[1] else 2)
            ].append(word)
        for index, column in enumerate(columns):
            entries.extend(
                (page_index, top, index, text) for top, text in _lines_of(column)
            )
    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    starts = [
        (page, top)
        for page, top, column, text in entries
        if column == 0 and (_START_CODE.match(text) or _START_NO_CODE.match(text))
    ]
    blocks = [RawBlock(page=page + 1) for page, _top in starts]
    for page, top, column, text in entries:
        # Columns 2 and 3 may sit a hair above the code line of their own row.
        owner = -1
        for index, (start_page, start_top) in enumerate(starts):
            if (page, top + (0 if column == 0 else LINE_TOLERANCE)) >= (
                start_page,
                start_top,
            ):
                owner = index
        if owner >= 0:
            getattr(blocks[owner], ("col1", "col2", "col3")[column]).append(text)
    return blocks


def parse_enr51_words(pages):
    """(zones, summary) from pages of words. Idempotent: same words, same output."""
    zones = []
    for block in blocks_from_words(pages):
        zone = parse_zone(block.col1, block.col2, block.col3)
        zone["page"] = block.page
        zones.append(zone)
    return zones, summarize(zones)


# --------------------------------------------------------------------------
# Amendment (every page carries its own "AMDT NR n" and date)
# --------------------------------------------------------------------------

_AMDT = re.compile(r"\bAMDT\s+NR\s+(\d{1,3})\b", re.I)
_AMDT_DATE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\b")
_MONTHS = {
    **{
        m: i
        for i, m in enumerate(
            "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1
        )
    },
    "ENE": 1,
    "ABR": 4,
    "AGO": 8,
    "DIC": 12,
}


def extract_amendment(pages):
    """(amdt_number, date) of the newest amendment printed on the pages, or ("", None).

    Each page carries its own amendment (a 2026 AIP still has pages of AMDT 44 or 49), so the
    amendment of the document is the highest number found, with the date printed beside it.
    """
    best = None
    for words in pages:
        amdt = date = None
        for _top, text in _lines_of(_clean_words(words)):
            match = _AMDT.search(text)
            if match and amdt is None:
                amdt = int(match.group(1))
            for day, mon, year in _AMDT_DATE.findall(text):
                month = _MONTHS.get(mon.upper())
                if month and date is None:
                    try:
                        date = datetime.date(int(year), month, int(day))
                    except ValueError:
                        date = None
        if (
            amdt is not None
            and date is not None
            and (best is None or (amdt, date) > best)
        ):
            best = (amdt, date)
    return (str(best[0]), best[1]) if best else ("", None)
