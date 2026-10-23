"""LV-361 phase 5: the AIP layer on the airspace map.

Everything here is synthetic: zones invented in the test, the synthetic KML for the Google side, and
no text or coordinate of the real AIP. What is fixed:

* with NO published AIP copy the payload, the ETag and the page are what they always were;
* with one, the AIP zone is drawn from the AIP and the Google shape of the same code steps back to
  the reference layer (off by default), the Google-only zones go to that layer too, and a zone
  approved «only as text» is listed and searchable but has no point and no geometry;
* nothing that is not approved AND published is ever served;
* the cross-check shows a distance and, only with a threshold, a verdict (never red);
* the script, run in Node against a stub of Leaflet, draws what it should and no more.
"""

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone, translation

from apps.airspace import aip_review, payload
from apps.airspace.kml_import import bounds_of
from apps.airspace.models import (
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)
from apps.core.testing import login_as as _login_as

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
NODE = shutil.which("node")
DATA, PAGE, NEAR = (
    reverse("airspace-data"),
    reverse("airspace-map"),
    reverse("airspace-near"),
)
VIEW = "view_airspacefeature"
EFFECTIVE = date(2026, 8, 6)


@pytest.fixture(autouse=True)
def english(settings):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = None
    with translation.override("en"):
        yield


_CLIENTS = {}


@pytest.fixture(autouse=True)
def fresh_clients():
    _CLIENTS.clear()  # `login_as` names the user after the permissions: one client per test and key


def login_as(*codenames, lang="en"):
    if codenames not in _CLIENTS:
        _CLIENTS[codenames] = _login_as(*codenames)
    client = _CLIENTS[codenames]
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = lang
    return client


def body(client_or_response):
    response = (
        client_or_response.get(DATA)
        if hasattr(client_or_response, "get")
        else client_or_response
    )
    return json.loads(response.content)


@pytest.fixture
def google(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    return AirspaceSnapshot.objects.get(is_current=True)


def square(lon, lat, size=0.2):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon, lat],
                [lon + size, lat],
                [lon + size, lat + size],
                [lon, lat + size],
                [lon, lat],
            ]
        ],
    }


EMPTY = {"type": "GeometryCollection", "geometries": []}


def aip_snapshot(*, amdt="67", published=True, sha="a", **kwargs):
    data = {
        "source_name": "AIP-Chile ENR 5.1",
        "fetched_at": timezone.now(),
        "sha256": sha * 64,
        "pdf_sha256": sha * 64,
        "attribution": "synthetic",
        "source_kind": "aip_enr51",
        "amdt_number": amdt,
        "effective_date": EFFECTIVE,
        "status": "published" if published else "draft",
        "is_current": published,
    }
    data.update(kwargs)
    return AirspaceSnapshot.objects.create(**data)


def aip_feature(snap, code, kind="restricted", geometry=None, **kwargs):
    geometry = square(-71.0, -34.0) if geometry is None else geometry
    shaped = payload.has_shape(geometry)
    bounds = bounds_of(geometry) if shaped else (0.0, 0.0, 0.0, 0.0)
    data = {
        "snapshot": snap,
        "source_key": f"aip-{code}-{kwargs.get('name', '')}",
        "content_hash": "h",
        "kind": kind,
        "code": code,
        "name": f"AIP zone {code}",
        "raw_name": f"AIP zone {code}",
        "geometry": geometry,
        "min_lat": bounds[0],
        "max_lat": bounds[1],
        "min_lon": bounds[2],
        "max_lon": bounds[3],
        "center_lat": round((bounds[0] + bounds[1]) / 2, 6),
        "center_lon": round((bounds[2] + bounds[3]) / 2, 6),
        "source_kind": "aip_enr51",
        "review_status": "approved",
        "is_active": True,
        "lateral_text": f"Lateral text of {code}",
        "vertical_limits_text": "FL 100 / GND",
        "schedule_text": "H24",
        "geometry_method": "polygon" if shaped else "arc",
    }
    data.update(kwargs)
    return AirspaceFeature.objects.create(**data)


@pytest.fixture
def published(google):
    """A published AIP copy: SC-R54 (also in Google), SC-X101 (AIP only), SC-P102 (an arc, text only)."""
    snap = aip_snapshot()
    both = aip_feature(snap, "SC-R54", geometry=square(-70.6, -33.4, 0.1))
    only = aip_feature(snap, "SC-X101", kind="prohibited")
    arc = aip_feature(snap, "SC-P102", kind="prohibited", geometry=EMPTY)
    return {"snap": snap, "both": both, "only": only, "arc": arc}


def google_row(code):
    return AirspaceFeature.objects.get(
        source_kind="google_mymaps", code=code, is_active=True
    )


def by_code(features, code, **match):
    rows = [
        f
        for f in features
        if f["code"] == code and all(f.get(k) == v for k, v in match.items())
    ]
    assert len(rows) == 1, (code, match, rows)
    return rows[0]


# ── without an AIP copy nothing changes ─────────────────────────────────────


@pytest.mark.django_db
def test_without_a_published_aip_the_payload_is_the_legacy_one_byte_for_byte(google):
    legacy = {
        "snapshot": payload.snapshot_payload(google),
        "features": [
            payload.feature_payload(f)
            for f in payload.active_features().order_by("kind", "code", "name")
        ],
    }
    client = login_as(VIEW)
    response = client.get(DATA)
    assert response.content.decode() == payload.dumps(legacy)
    assert response["ETag"] == f'"{google.sha256}"'
    data = json.loads(response.content)
    assert "aip" not in data["snapshot"]
    assert not any(
        {"source_kind", "ref", "shadowed", "cross", "no_shape"} & set(f)
        for f in data["features"]
    )


@pytest.mark.django_db
def test_without_a_published_aip_the_page_says_nothing_about_it(google):
    html = login_as(VIEW).get(PAGE).content.decode()
    for hint in (
        "AIP-Chile copy",
        "air-legend-ref-group",
        "air-sources",
        "Check the current NOTAM/SUP.",
        "on record",
    ):
        assert hint not in html, hint
    assert re.search(r"<dt>(?:<svg.*?</svg>)?Restricted zone</dt><dd>2</dd>", html)


@pytest.mark.django_db
def test_a_draft_or_unpublished_aip_changes_nothing(google):
    draft = aip_snapshot(published=False, sha="d")
    aip_feature(draft, "SC-R54", name="DRAFT-ONLY NAME", is_active=False)
    aip_feature(draft, "SC-Z999", name="SECOND DRAFT NAME")
    client = login_as(VIEW)
    response = client.get(DATA)
    assert response["ETag"] == f'"{google.sha256}"'
    assert "DRAFT-ONLY" not in response.content.decode()
    assert "SECOND DRAFT" not in response.content.decode()
    assert "aip" not in json.loads(response.content)["snapshot"]


# ── with an AIP copy ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_aip_only_zone_is_served_from_the_aip_with_its_source(published):
    data = body(login_as(VIEW))
    zone = by_code(data["features"], "SC-X101")
    assert zone["source_kind"] == "aip_enr51"
    assert zone["geometry"]["type"] == "Polygon" and len(zone["bbox"]) == 4
    assert zone["vertical"] == "FL 100 / GND" and zone["schedule"] == "H24"
    assert zone["text"] == "Lateral text of SC-X101"
    assert zone["folder"] == payload.AIP_FOLDER
    assert "ref" not in zone and "shadowed" not in zone
    aip = data["snapshot"]["aip"]
    assert aip["amdt"] == "67" and aip["effective_date"] == "2026-08-06"
    assert aip["outdated"] is False and aip["latest_known_amdt"] == "67"


@pytest.mark.django_db
def test_a_zone_in_both_sources_is_drawn_from_the_aip_and_google_steps_back(published):
    features = body(login_as(VIEW))["features"]
    aip = by_code(features, "SC-R54", source_kind="aip_enr51")
    google_copy = by_code(features, "SC-R54", source_kind="google_mymaps")
    assert aip["geometry"] != google_copy["geometry"]
    assert "ref" not in aip
    assert google_copy["ref"] is True and google_copy["shadowed"] is True
    assert google_copy["id"] == str(google_row("SC-R54").pk)


@pytest.mark.django_db
def test_the_google_only_zones_go_to_the_reference_layer_but_stay_searchable(published):
    features = body(login_as(VIEW))["features"]
    only_google = by_code(features, "SC-D66")
    assert only_google["ref"] is True and "shadowed" not in only_google
    assert only_google["source_kind"] == "google_mymaps"
    naval = [f for f in features if f["kind"] == "naval"]
    assert naval and all(f["ref"] is True for f in naval)
    # Aerodromes, airstrips and the FIR boundary are the Google photo, untouched.
    for f in features:
        if f["kind"] in ("aerodrome", "airport", "airstrip", "fir_boundary"):
            assert "ref" not in f and f["source_kind"] == "google_mymaps"


@pytest.mark.django_db
def test_an_arc_approved_only_as_text_has_no_point_and_no_geometry_but_its_text(
    published,
):
    features = body(login_as(VIEW))["features"]
    arc = by_code(features, "SC-P102")
    assert arc["no_shape"] == "arc"
    for key in ("geometry", "bbox"):
        assert key not in arc
    assert arc["lat"] is None and arc["lon"] is None and arc["dms"] == ""
    assert arc["text"] == "Lateral text of SC-P102" and arc["vertical"]
    # It is not a point at 0,0: the near query never finds it.
    near = json.loads(
        login_as(VIEW).get(NEAR, {"lat": 0.0, "lon": 0.0, "radius_km": 5}).content
    )
    ids = {e["id"] for key in ("containing", "touching", "near") for e in near[key]}
    assert str(published["arc"].pk) not in ids


@pytest.mark.django_db
def test_nothing_unapproved_unpublished_or_archived_of_the_aip_is_ever_served(
    published,
):
    snap = published["snap"]
    aip_feature(snap, "SC-W1", name="PENDING NAME", review_status="pending")
    aip_feature(snap, "SC-W2", name="REJECTED NAME", review_status="rejected")
    aip_feature(snap, "SC-W3", name="NEEDS NAME", review_status="needs_review")
    aip_feature(snap, "SC-W4", name="ARCHIVED NAME", is_active=False)
    other = aip_snapshot(published=False, amdt="68", sha="b")
    aip_feature(other, "SC-W5", name="NEXT AMENDMENT NAME")
    client = login_as(VIEW)
    raw = client.get(DATA).content.decode()
    for name in (
        "PENDING NAME",
        "REJECTED NAME",
        "NEEDS NAME",
        "ARCHIVED NAME",
        "NEXT AMENDMENT NAME",
    ):
        assert name not in raw, name
    assert "NEXT AMENDMENT NAME" not in client.get(PAGE).content.decode()
    assert not payload.active_aip_features().filter(name__contains="NAME").exists()


@pytest.mark.django_db
def test_the_counts_count_a_zone_in_both_sources_once(published):
    html = login_as(VIEW).get(PAGE).content.decode()

    def count(label):
        match = re.search(rf"<dt>(?:<svg.*?</svg>)?{label}</dt><dd>(\d+)</dd>", html)
        return int(match.group(1))

    # Google alone has two restricted zones (R54 and R41): the AIP's R54 takes the place of Google's
    # R54 (once) and R41 is still there as «Google only».
    searchable = payload.served_set().searchable()
    kinds = [f.kind for f in searchable]
    assert count("Restricted zone") == kinds.count("restricted") == 2
    assert count("Prohibited zone") == kinds.count("prohibited")
    assert len({f.pk for f in searchable}) == len(searchable)
    shadowed = [f for f, role in payload.served_set().google_rows if role == "shadowed"]
    assert [f.code for f in shadowed] == ["SC-R54"]
    assert shadowed[0] not in searchable
    # The strip says which source feeds what.
    assert re.search(
        r"Zones: 3 come from the AIP and \d+ only from the Google map", html
    )
    assert "1 AIP zone(s) are text only" in html


# ── the ETag ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_etag_is_a_digest_of_both_photos_and_changes_when_either_does(published):
    client = login_as(VIEW)
    first = client.get(DATA)
    etag = first["ETag"]
    assert etag != f'"{published["snap"].sha256}"' and len(etag) == 66
    assert client.get(DATA, HTTP_IF_NONE_MATCH=etag).status_code == 304
    assert client.get(DATA, HTTP_IF_NONE_MATCH='W/"zz", ' + etag).status_code == 304

    AirspaceSnapshot.objects.filter(pk=published["snap"].pk).update(sha256="c" * 64)
    assert client.get(DATA)["ETag"] != etag
    assert client.get(DATA, HTTP_IF_NONE_MATCH=etag).status_code == 200
    AirspaceSnapshot.objects.filter(pk=published["snap"].pk).update(
        sha256=published["snap"].sha256
    )
    assert client.get(DATA)["ETag"] == etag
    google = AirspaceSnapshot.objects.get(source_kind="google_mymaps", is_current=True)
    AirspaceSnapshot.objects.filter(pk=google.pk).update(sha256="e" * 64)
    assert client.get(DATA)["ETag"] != etag


@pytest.mark.django_db
def test_publishing_an_aip_copy_changes_the_etag_from_the_google_only_one(google):
    client = login_as(VIEW)
    before = client.get(DATA)["ETag"]
    assert before == f'"{google.sha256}"'
    snap = aip_snapshot(published=False, status="in_review", is_current=False)
    aip_feature(snap, "SC-X101", kind="prohibited", is_active=False)
    assert client.get(DATA)["ETag"] == before  # a draft is not served
    user = get_user_model().objects.create_user("reviewer", password="pw-test-1234")
    aip_review.publish(snap, user)
    after = client.get(DATA)["ETag"]
    assert after != before
    assert client.get(DATA, HTTP_IF_NONE_MATCH=before).status_code == 200


@pytest.mark.django_db
def test_the_threshold_changes_the_etag_because_it_changes_the_answer(
    published, settings
):
    client = login_as(VIEW)
    before = client.get(DATA)["ETag"]
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = 150
    assert client.get(DATA)["ETag"] != before


# ── permissions (LV-268) ────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("url", [PAGE, DATA, NEAR + "?lat=-33&lon=-70"])
def test_the_routes_stay_403_without_the_view_permission(published, url):
    assert login_as().get(url).status_code == 403
    assert login_as("view_userweatherlocation").get(url).status_code == 403


@pytest.mark.django_db
def test_anonymous_still_goes_to_the_login(published, client):
    response = client.get(DATA)
    assert response.status_code == 302 and "login" in response["Location"]


# ── near and the screen agree ───────────────────────────────────────────────


@pytest.mark.django_db
def test_near_answers_with_the_zone_the_map_draws(published):
    client = login_as(VIEW)
    inside = json.loads(client.get(NEAR, {"lat": -33.35, "lon": -70.55}).content)
    containing = {e["id"] for e in inside["containing"]}
    assert str(published["both"].pk) in containing
    assert (
        str(google_row("SC-R54").pk) not in containing
    )  # shadowed: the same zone twice
    # A Google-only zone is still found.
    d66 = json.loads(client.get(NEAR, {"lat": -33.19, "lon": -70.42}).content)
    assert str(google_row("SC-D66").pk) in {e["id"] for e in d66["containing"]}


# ── the cross-check ─────────────────────────────────────────────────────────


@pytest.fixture
def crossed(published):
    AirspaceCrossCheck.objects.create(
        snapshot=published["snap"],
        code="SC-R54",
        aip_feature=published["both"],
        google_feature=google_row("SC-R54"),
        max_vertex_m=123.4,
        median_m=40.0,
        result="measured",
    )
    return published


@pytest.mark.django_db
def test_without_a_threshold_the_cross_check_is_a_distance_with_no_verdict(crossed):
    features = body(login_as(VIEW))["features"]
    assert by_code(features, "SC-R54", source_kind="aip_enr51")["cross"] == {
        "m": 123,
        "verdict": None,
    }
    assert "cross" not in by_code(features, "SC-X101")


@pytest.mark.django_db
def test_with_a_threshold_the_verdict_is_computed_now_not_read_from_the_old_row(
    crossed, settings
):
    client = login_as(VIEW)
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = 100
    zone = by_code(body(client)["features"], "SC-R54", source_kind="aip_enr51")
    assert zone["cross"] == {"m": 123, "verdict": "discrepancy"}
    assert body(client)["snapshot"]["aip"]["threshold_m"] == 100.0
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = 500
    zone = by_code(body(client)["features"], "SC-R54", source_kind="aip_enr51")
    assert zone["cross"]["verdict"] == "match"


@pytest.mark.django_db
def test_a_cross_check_against_a_google_shape_that_is_no_longer_current_is_not_shown(
    crossed,
):
    AirspaceFeature.objects.filter(pk=google_row("SC-R54").pk).update(is_active=False)
    features = body(login_as(VIEW))["features"]
    assert "cross" not in by_code(features, "SC-R54", source_kind="aip_enr51")


# ── freshness and attribution ───────────────────────────────────────────────


@pytest.mark.django_db
def test_the_attribution_names_the_amendment_and_the_notam_warning_in_both_languages(
    published,
):
    html = login_as(VIEW).get(PAGE).content.decode()
    assert (
        "Source: AIP-Chile, DGAC, AMDT NR 67 (06 AUG 2026), ENR 5.1. For reference only; check the current NOTAM/SUP."
        in html
    )
    assert html.count('class="env-referential"') == 1
    es = login_as(VIEW, lang="es").get(PAGE).content.decode()
    assert (
        "Fuente: AIP-Chile, DGAC, AMDT NR 67 (06 AUG 2026), ENR 5.1. Referencial; consulte NOTAM/SUP vigentes."
        in es
    )
    assert "Consulte los NOTAM/SUP vigentes." in es
    assert es.count('class="env-referential"') == 1


@pytest.mark.django_db
def test_the_aip_is_fresh_when_no_newer_amendment_is_on_record(published):
    html = login_as(VIEW).get(PAGE).content.decode()
    row = re.search(r'<p class="air-source[^"]*">.*?AMDT 67.*?</p>', html, re.S).group(
        0
    )
    assert "air-source--stale" not in row and "No newer amendment on record" in row
    assert "●" in row and "Check the current NOTAM/SUP." in row
    assert "air-photo--stale" not in html


@pytest.mark.django_db
def test_a_newer_amendment_on_record_turns_the_published_copy_amber_with_symbol_and_word(
    published,
):
    aip_snapshot(published=False, amdt="68", sha="b", effective_date=date(2026, 11, 26))
    html = login_as(VIEW).get(PAGE).content.decode()
    row = re.search(r'<p class="air-source[^"]*">.*?AMDT 67.*?</p>', html, re.S).group(
        0
    )
    assert "air-source--stale" in row and "air-fresh--stale" in row
    assert "Newer amendment on record: AMDT 68 (26-11-2026)" in row
    assert "▲" in row and "Check the current NOTAM/SUP." in row  # the warning stays
    assert "air-photo--stale" in html
    info = body(login_as(VIEW))["snapshot"]["aip"]
    assert info["outdated"] is True and info["latest_known_amdt"] == "68"


@pytest.mark.django_db
def test_the_latest_known_amendment_is_never_made_up(published):
    # No other snapshot: the latest known is the copy's own.
    info = payload.aip_freshness(published["snap"])
    assert info == {
        "latest_known_amdt": "67",
        "latest_known_date": "2026-08-06",
        "outdated": False,
    }
    # A non-numeric amendment cannot be compared, so it is never flagged.
    aip_snapshot(published=False, amdt="abc", sha="b")
    assert payload.aip_freshness(published["snap"])["outdated"] is False
    # The Google snapshots are not amendments of the AIP.
    AirspaceSnapshot.objects.filter(source_kind="google_mymaps").update(
        amdt_number="99"
    )
    assert payload.aip_freshness(published["snap"])["outdated"] is False


# ── weight ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_eighty_aip_zones_plus_google_stay_inside_a_ceiling(google):
    base = len(login_as(VIEW).get(DATA).content)
    snap = aip_snapshot()
    ring = [[-70.0 + i * 0.01, -33.0 + ((i * 7) % 5) * 0.01] for i in range(14)]
    ring.append(list(ring[0]))
    for n in range(80):
        aip_feature(
            snap,
            f"SC-{'PRD'[n % 3]}{200 + n}",
            kind=("prohibited", "restricted", "danger")[n % 3],
            geometry={"type": "Polygon", "coordinates": [ring]},
        )
    size = len(login_as(VIEW).get(DATA).content)
    assert size < 120_000, size
    assert size - base < 100_000  # roughly 1 KB per zone of 15 vertices
    print(f"data.json: google {base} B, google + 80 AIP zones {size} B")


# ── contrast, calculated ────────────────────────────────────────────────────

CSS = (ROOT / "static" / "css" / "airspace.css").read_text(encoding="utf-8")
APP = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")


def _luminance(hex_color):
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _app_tokens(name):
    """[light, dark] hex of a base token (the file defines it once per theme, light first)."""
    found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", APP)
    assert len(found) >= 2, name
    return found[0], found[-1]


def test_the_reference_line_reads_against_the_halo_and_against_black():
    line = re.search(r"--id-air-line-ref:\s*(#[0-9a-fA-F]{6})", CSS).group(1)
    halo = re.search(r"--id-air-halo:\s*(#[0-9a-fA-F]{6})", CSS).group(1)
    assert contrast(line, halo) >= 3 and contrast(line, "#000000") >= 3


@pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
@pytest.mark.parametrize(
    "tone", ["advisory", "nominal", "warning"], ids=["aip", "google", "discrepancy"]
)
def test_the_source_chips_and_the_discrepancy_text_are_readable_in_both_themes(
    tone, theme
):
    text = _app_tokens(f"sev-{tone}-text")[theme]
    background = _app_tokens(f"sev-{tone}-bg")[theme]
    assert contrast(text, background) >= 4.5
    if tone == "warning":  # the discrepancy line sits on the card, not on a chip
        assert contrast(text, _app_tokens("ac-surface")[theme]) >= 4.5


def test_a_discrepancy_is_never_drawn_red():
    for rule in re.findall(r"\.air-(?:src|cross)[^{]*\{[^}]*\}", CSS):
        assert "critical" not in rule and "danger" not in rule, rule
        assert not re.search(r"#(?:f|e)[0-9a-f]0{4}\b", rule, re.I), rule


# ── the template and the catalogue ──────────────────────────────────────────


@pytest.mark.django_db
def test_the_new_pieces_are_translated_to_spanish(published):
    html = login_as(VIEW, lang="es").get(PAGE).content.decode()
    for text in (
        "Copia del AIP-Chile: AMDT 67 del 06-08-2026",
        "Sin enmienda más reciente registrada",
        "Referencia",
        "Zonas: 3 vienen del AIP",
        "son solo texto",
    ):
        assert text in html, text
    config = json.loads(
        re.search(
            r'<script id="air-config" type="application/json">(.*?)</script>',
            html,
            re.S,
        ).group(1)
    )["i18n"]
    assert config["badgeGoogleOnly"] == "Solo mapa Google (no está en el AIP vigente)"
    assert config["crossDiff"] == "Diferencia con Google: {m} m"
    assert config["noShapeArc"].startswith("Sin forma dibujada: arco o sector")


# ── the script, in Node ─────────────────────────────────────────────────────

NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', async () => {
  const input = JSON.parse(raw);
  const tick = async () => { for (let i = 0; i < 8; i += 1) { await new Promise(r => setImmediate(r)); } };
  const created = [];
  const onMap = new Set();
  const nodes = {};
  const docListeners = {};
  const stub = () => ({
    textContent: '', value: '', checked: false, hidden: false, dataset: {}, style: {}, options: {},
    listeners: {}, children: [], firstChild: null, className: '', innerHTML: '', title: '',
    classList: { toggle() {}, add() {}, remove() {} },
    appendChild(c) { this.children.push(c); return c; }, insertBefore() {},
    setAttribute() {}, removeAttribute() {}, focus() {}, closest() { return null; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
  });
  const document = {
    getElementById(id) {
      if (id === 'air-config') { return { textContent: JSON.stringify(input.cfg) }; }
      return nodes[id] = nodes[id] || stub();
    },
    createElement: stub, createElementNS: stub, querySelector() { return null; },
    addEventListener(n, f) { (docListeners[n] = docListeners[n] || []).push(f); },
    documentElement: stub(),
  };
  const make = kind => (a, b) => {
    const l = Object.assign({ kind, options: b || {}, args: a,
      on() { return l; }, bindTooltip() { return l; }, setLatLngs() {}, setStyle() {}, eachLayer() {},
      bringToFront() {} }, kind === 'geoJSON' ? { geometry: a } : {});
    l.addTo = () => { onMap.add(l); return l; };
    created.push(l);
    return l;
  };
  const map = { on() { return map; }, getSize: () => ({ x: 500, y: 400 }), fitBounds() {}, setView() {},
    addLayer() {}, removeLayer(l) { onMap.delete(l); }, createPane() {}, getZoom: () => 9,
    doubleClickZoom: { enable() {}, disable() {} } };
  const L = {
    map: () => map, canvas: () => ({}), svg: () => ({ _container: stub() }),
    tileLayer: make('tile'), control: { layers: make('control') },
    marker: make('marker'), circleMarker: make('circleMarker'), polyline: make('polyline'),
    circle: make('circle'), layerGroup: make('group'), divIcon: o => o, DomEvent: { stopPropagation() {} },
    geoJSON: make('geoJSON'),
  };
  const errors = [];
  const window = {
    L, AirspaceSearch: require('./static/js/airspace-search.js'), location: { search: '' },
    console: { error: (...a) => errors.push(a.join(' ')) }, setTimeout, clearTimeout,
  };
  class MutationObserver { observe() {} }
  const code = fs.readFileSync('./static/js/airspace-map.js', 'utf8');
  new Function('window', 'document', 'L', 'fetch', 'MutationObserver', 'getComputedStyle', 'console', code)(
    window, document, L, async () => ({ ok: true, status: 200, json: async () => input.data }),
    MutationObserver, () => ({ getPropertyValue: () => '' }), window.console);
  await tick();

  const texts = (node, out = []) => {
    if (node.textContent && !(node.children || []).length) { out.push(node.textContent); }
    (node.children || []).forEach(c => texts(c, out));
    return out;
  };
  const rows = () => nodes['air-results'].children.map(li => {
    const button = li.children[0];
    return { id: button.dataset.id, text: texts(button).join(' | '), classes: JSON.stringify(
      (function walk(n, acc) { acc.push(n.className); (n.children || []).forEach(c => walk(c, acc)); return acc; })(button, [])) };
  });
  const firstCoordinate = l => {
    const g = l.geometry;
    let c = g.coordinates || (g.geometries && g.geometries[0].coordinates);
    while (Array.isArray(c) && Array.isArray(c[0])) { c = c[0]; }
    return c;
  };
  const out = { errors };
  const lines = created.filter(l => l.kind === 'geoJSON');
  out.drawn = lines.map(l => ({ first: firstCoordinate(l), on: onMap.has(l) }));
  out.status = nodes['air-status'].textContent;
  out.rows = rows();
  out.markers = created.filter(l => l.kind === 'marker').map(l => ({
    cls: l.options.icon && l.options.icon.className, latlng: l.args, on: onMap.has(l) }));
  const legend = nodes['air-legend-ref'];
  out.refLegend = { items: legend.children.length, hidden: nodes['air-legend-ref-group'].hidden,
    text: legend.children.length ? texts(legend.children[0]) : [] };

  // Click a row (the document listener reads `event.target.closest('.air-row')`).
  const click = id => {
    const row = nodes['air-results'].children.map(li => li.children[0]).find(b => b.dataset.id === id);
    (docListeners.click || []).forEach(f => f({ target: { closest: () => row } }));
  };
  const fiche = () => ({
    name: nodes['air-fiche-name'].textContent, source: nodes['air-f-source'].textContent,
    sourceHidden: nodes['air-f-source'].hidden, sourceClass: nodes['air-f-source'].className,
    cross: nodes['air-f-cross'].textContent, crossHidden: nodes['air-f-cross'].hidden,
    crossClass: nodes['air-f-cross'].className, crossTitle: nodes['air-f-cross'].title,
    noShape: nodes['air-f-noshape-text'].textContent, noShapeHidden: nodes['air-f-noshape'].hidden,
    center: nodes['air-f-center'].textContent, text: nodes['air-f-text'].textContent });
  // Switch the reference layer on with its box and see what comes onto the map.
  if (input.toggle && legend.children.length) {
    const box = legend.children[0].children[0];
    const before = [...onMap].length;
    box.checked = true; box.listeners.change[0]();
    out.refToggle = { before, after: [...onMap].length,
      hint: nodes['air-tool-hint'].textContent };
    out.drawnAfter = lines.map(l => ({ first: firstCoordinate(l), on: onMap.has(l) }));
  }
  out.fiche = {};
  const onBefore = [...onMap].length;
  for (const id of input.click) { click(id); out.fiche[id] = fiche(); }
  out.clickEffect = { before: onBefore, after: [...onMap].length };
  // The kind and text search: the shadowed Google copy is never a second result.
  nodes['air-results'].children.length = 0;  // the stub does not clear on 	extContent = ''
  nodes['air-q'].value = 'SC-R54';
  (nodes['air-q'].listeners.input || []).forEach(f => f());
  await new Promise(r => setTimeout(r, 200));
  out.searchRows = rows().map(r => r.id);
  process.stdout.write(JSON.stringify(out));
});
"""


@pytest.fixture
def node_run(crossed, settings):
    if NODE is None:
        pytest.skip("Node no está instalado")
    from apps.airspace.views import tab_config

    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = None
    cfg = tab_config(None)
    cfg["tileProviders"] = []
    cfg["i18n"]["resultsCount"] = "{n} results"
    data = json.loads(login_as(VIEW).get(DATA).content)
    ids = {
        "both": str(crossed["both"].pk),
        "only": str(crossed["only"].pk),
        "arc": str(crossed["arc"].pk),
        "d66": str(google_row("SC-D66").pk),
    }

    def run(data_override=None, toggle=False, click=None):
        result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
            [NODE, "-e", NODE_SCRIPT],
            input=json.dumps(
                {
                    "cfg": cfg,
                    "data": data_override or data,
                    "toggle": toggle,
                    "click": [ids["both"], ids["arc"], ids["d66"]]
                    if click is None
                    else click,
                }
            ),
            capture_output=True,
            encoding="utf-8",
            cwd=ROOT,
            timeout=60,
            check=True,
        )
        return json.loads(result.stdout)

    return run, data, ids


def test_the_script_draws_the_aip_and_keeps_the_reference_layer_off(node_run):
    run, data, ids = node_run
    out = run()
    assert out["errors"] == []
    by_id = {f["id"]: f for f in data["features"]}
    first = lambda f: f["geometry"]["coordinates"][0][0]  # noqa: E731
    shadowed = [f for f in data["features"] if f.get("shadowed")]
    refs = [f for f in data["features"] if f.get("ref")]
    drawn_on = [d["first"] for d in out["drawn"] if d["on"]]
    drawn_off = [d["first"] for d in out["drawn"] if not d["on"]]
    # The AIP's own outlines are on the map; every reference outline is drawn but OFF.
    assert first(by_id[ids["both"]]) in drawn_on
    assert first(by_id[ids["only"]]) in drawn_on
    for f in refs:
        if "geometry" in f and f["geometry"].get("coordinates"):
            assert first(f) in drawn_off and first(f) not in drawn_on, f["code"]
    assert shadowed and first(shadowed[0]) in drawn_off
    # The arc has no shape and no marker: nothing at 0,0 (no centre is ever made up for it).
    assert [
        m for m in out["markers"] if m["latlng"] is None or None in m["latlng"]
    ] == []
    assert [m for m in out["markers"] if m["latlng"] == [0, 0]] == []
    assert [d for d in out["drawn"] if d["first"] in ([0, 0], None)] == []
    assert out["errors"] == []


def test_the_arc_and_the_google_copy_do_not_add_results_but_the_arc_is_listed(node_run):
    run, data, ids = node_run
    out = run()
    listed = {r["id"] for r in out["rows"]}
    assert ids["arc"] in listed  # text-only zones are searchable
    shadowed = [f["id"] for f in data["features"] if f.get("shadowed")]
    assert shadowed and not set(shadowed) & listed
    total = len([f for f in data["features"] if not f.get("shadowed")])
    airstrips = len([f for f in data["features"] if f["kind"] == "airstrip"])
    assert out["status"] == f"{total - airstrips} results"
    assert out["searchRows"].count(ids["both"]) == 1
    assert shadowed[0] not in out["searchRows"]


def test_rows_and_sheet_carry_the_source_badge_and_the_distance_without_a_verdict(
    node_run,
):
    run, data, ids = node_run
    out = run()
    row = next(r for r in out["rows"] if r["id"] == ids["both"])
    assert "● AIP · AMDT 67 (06-08-2026)" in row["text"]
    assert "Difference from Google: 123 m" in row["text"]
    assert "air-cross--plain" in row["classes"] and "discrepancy" not in row["classes"]
    google_only = next(r for r in out["rows"] if r["id"] == ids["d66"])
    assert "○ Google map only (not in the current AIP)" in google_only["text"]
    sheet = out["fiche"][ids["both"]]
    assert (
        sheet["source"] == "● AIP · AMDT 67 (06-08-2026)" and not sheet["sourceHidden"]
    )
    assert "air-src--aip" in sheet["sourceClass"]
    assert (
        sheet["cross"] == "Difference from Google: 123 m" and not sheet["crossHidden"]
    )
    assert "plain" in sheet["crossClass"] and sheet["crossTitle"]
    assert "▲" not in sheet["cross"] and "●" not in sheet["cross"]
    d66 = out["fiche"][ids["d66"]]
    assert d66["source"].startswith("○ Google map only") and d66["crossHidden"]


def test_a_zone_given_only_as_text_shows_its_text_and_the_reason_it_has_no_outline(
    node_run,
):
    run, data, ids = node_run
    sheet = run()["fiche"][ids["arc"]]
    assert sheet["noShapeHidden"] is False
    assert (
        sheet["noShape"] == "No outline drawn: arc or sector, needs an external centre"
    )
    assert (
        sheet["text"] == "Lateral text of SC-P102"
        and sheet["center"] == "Not stated in the source"
    )
    assert run()["fiche"][ids["both"]]["noShapeHidden"] is True


def test_with_a_threshold_the_verdict_is_symbol_plus_text_and_amber(node_run):
    run, data, ids = node_run
    for feature in data["features"]:
        if feature["id"] == ids["both"]:
            feature["cross"]["verdict"] = "discrepancy"
    data["snapshot"]["aip"]["threshold_m"] = 100
    sheet = run(data)["fiche"][ids["both"]]
    assert sheet["cross"] == "▲ Discrepancy with Google: 123 m (threshold 100 m)"
    assert "air-cross--discrepancy" in sheet["crossClass"]
    for feature in data["features"]:
        if feature["id"] == ids["both"]:
            feature["cross"]["verdict"] = "match"
    sheet = run(data)["fiche"][ids["both"]]
    assert sheet["cross"] == "● Matches Google: 123 m (threshold 100 m)"
    assert "air-cross--match" in sheet["crossClass"]


def test_the_reference_layer_has_its_own_legend_item_and_turns_on_with_its_box(
    node_run,
):
    run, data, ids = node_run
    out = run(toggle=True, click=[])
    refs = [f for f in data["features"] if f.get("ref")]
    assert out["refLegend"]["hidden"] is False and out["refLegend"]["items"] == 1
    assert out["refLegend"]["text"][-2:] == [
        "Google reference (off by default)",
        str(len(refs)),
    ]
    assert out["refToggle"]["after"] > out["refToggle"]["before"]
    assert out["refToggle"]["hint"] == "Google reference (off by default): shown"
    assert all(
        d["on"] for d in out["drawnAfter"] if d["first"]
    )  # now every outline is on


def test_choosing_a_google_only_zone_from_the_list_brings_its_layer_on(node_run):
    run, data, ids = node_run
    selected = run(click=[ids["d66"]])["clickEffect"]
    assert selected["after"] > selected["before"]
    # An AIP zone is already on the map: choosing it adds nothing.
    own = run(click=[ids["both"]])["clickEffect"]
    assert own["after"] == own["before"]


def test_without_an_aip_the_script_shows_no_badge_and_no_reference_legend(google):
    if NODE is None:
        pytest.skip("Node no está instalado")
    from apps.airspace.views import tab_config

    cfg = tab_config(None)
    cfg["tileProviders"] = []
    data = json.loads(login_as(VIEW).get(DATA).content)
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps({"cfg": cfg, "data": data, "click": []}),
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    out = json.loads(result.stdout)
    assert out["errors"] == []
    assert out["refLegend"]["items"] == 0
    assert not any(
        "AIP" in r["text"] or "Google map only" in r["text"] for r in out["rows"]
    )
    assert not any(
        "air-src" in r["classes"] or "air-cross" in r["classes"] for r in out["rows"]
    )


def test_the_script_keeps_its_guards():
    js = (ROOT / "static" / "js" / "airspace-map.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    assert "innerHTML" not in code and code.count("fetch(") == 5
    # A zone without a shape is skipped before anything is created for it.
    assert re.search(
        r"function draw\(entry\) \{\s*var kind = entry\.kind;(?:\s*//[^\n]*)*\s*if \(entry\.no_shape\)",
        code,
    )
