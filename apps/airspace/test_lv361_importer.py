"""LV-361 phase 3: `import_aip_enr5`, the draft snapshot and the cross-check with the Google map.

Everything is SYNTHETIC: zone codes, names, coordinates and contacts are invented with the shape of
the source. The real ENR 5.1 PDF and its text belong to the DGAC (and its remarks carry personal
data), so neither is in git. The PDF layer is replaced by a function that returns words with a
bounding box, which is the contract `aip_pdf.read_pages` has with the parser; one test does go
through a real PDF generated here with reportlab, when pdfplumber is installed.
"""

import datetime
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from apps.airspace import aip_import, aip_parser, aip_pdf, payload
from apps.airspace.models import (
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)

pytestmark = pytest.mark.django_db

SENTINELS = (
    "centinela.uno@test.com",
    "centinela.dos@test.com",
    "5551234567",
    "29222117",
    "Cte. Zeta Quimera",
)
REMARKS_WITH_CONTACTS = (
    "H24. Coordinar con Cte. Zeta Quimera, fono +56 2 5551234567, anexo 4455, "
    "correo centinela.uno@test.com y centinela.dos@test.com. Consultas 29222117. Horario 0800-1700 LT."
)


# ── synthetic words ─────────────────────────────────────────────────────────


def _word(text, x0, top):
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + 4 * len(text),
        "top": top,
        "bottom": top + 8,
    }


def _row(text, x0, top):
    return [_word(t, x0 + i * 14, top) for i, t in enumerate(text.split())]


def _zone_words(zone, top):
    """The three columns of one zone starting at `top`; returns (words, next_top)."""
    words = []
    for i, line in enumerate(zone["col1"]):
        words += _row(line, 85, top + 12 * i)
    for i, line in enumerate(zone.get("col2", ["UNL", "GND"])):
        words += _row(line, 300, top + 12 * i)
    for i, line in enumerate(zone.get("col3", ["H24"])):
        words += _row(line, 393, top + 12 * i)
    return words, top + 12 * max(len(zone["col1"]), 3) + 18


def make_pages(zones, amdt=67, date="06 AUG 2026"):
    words = _row("AIP-CHILE ENR 5.1-9", 85, 26) + _row(f"VOLUMEN I {date}", 85, 37)
    words += _row(f"AIS - CHILE AMDT NR {amdt}", 85, 700)
    words += _row("Identificación, nombre", 101, 45) + _row("Observaciones", 421, 45)
    words += [_word("1", 173, 60), _word("2", 324, 60), _word("3", 455, 60)]
    top = 100
    for zone in zones:
        extra, top = _zone_words(zone, top)
        words += extra
    return [words]


SQUARE = [
    "30 00 00 S 70 00 00 W",
    "30 00 00 S 69 00 00 W",
    "31 00 00 S 69 00 00 W",
    "31 00 00 S 70 00 00 W",
]
BOWTIE = [SQUARE[0], SQUARE[2], SQUARE[1], SQUARE[3]]
INTRO = "área definida por las siguientes coordenadas:"

ZONE_P901 = {
    "col1": ["SC-P901 FIR SANTIAGO", "Zona Sintetica Uno", INTRO, *SQUARE],
    "col3": [REMARKS_WITH_CONTACTS],
}
ZONE_P902 = {  # the vertex order crosses itself
    "col1": ["SC-P902 FIR SANTIAGO", "Zona Sintetica Dos", INTRO, *BOWTIE],
}
ZONE_R903 = {
    "col1": [
        "SC-R903 FIR SANTIAGO",
        "Zona Sintetica Tres",
        "Círculo de 1 NM de radio centrado en:",
        "34 00 00 S 70 30 00 W",
    ],
    "col2": ["FL 100", "GND"],
}
ZONE_R904 = {  # an arc: no geometry, the centre is not in the text
    "col1": [
        "SC-R904 FIR SANTIAGO",
        "Zona Sintetica Cuatro",
        "Límites laterales: arco de 10 NM centrado en el VOR/DME ABC",
    ],
}
BASE_ZONES = [ZONE_P901, ZONE_P902, ZONE_R903, ZONE_R904]


@pytest.fixture
def words(monkeypatch):
    """Control what the PDF layer returns, whatever bytes arrive."""
    state = {"pages": make_pages(BASE_ZONES)}

    def fake(source):
        if isinstance(state["pages"], Exception):
            raise state["pages"]
        return state["pages"]

    monkeypatch.setattr(aip_pdf, "read_pages", fake)
    return state


def pdf_file(tmp_path, tag="a"):
    path = tmp_path / f"enr51-{tag}.pdf"
    path.write_bytes(f"%PDF-1.4 synthetic {tag}\n".encode())
    return path


def run(*args, **options):
    out = StringIO()
    call_command("import_aip_enr5", *args, stdout=out, **options)
    return out.getvalue()


def aip_snapshots():
    return AirspaceSnapshot.objects.filter(source_kind="aip_enr51")


def aip_features():
    return AirspaceFeature.objects.filter(source_kind="aip_enr51")


# ── a synthetic Google snapshot to compare with ─────────────────────────────


def google_snapshot():
    return AirspaceSnapshot.objects.create(
        source_name="synthetic google",
        fetched_at=timezone.now(),
        sha256="g" * 64,
        attribution="synthetic",
        is_current=True,
    )


def google_feature(snap, key, code, kind, ring=None, **kwargs):
    ring = ring or []
    lons = [p[0] for p in ring] or [-70.0]
    lats = [p[1] for p in ring] or [-33.0]
    data = {
        "snapshot": snap,
        "source_kind": "google_mymaps",
        "review_status": "approved",
        "source_key": key,
        "content_hash": key,
        "kind": kind,
        "code": code,
        "name": f"Google {code}",
        "raw_name": f"Google {code}",
        "geometry": {"type": "Polygon", "coordinates": [ring]}
        if ring
        else {"type": "Point", "coordinates": [-70.0, -33.0]},
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
        "center_lat": sum(lats) / len(lats),
        "center_lon": sum(lons) / len(lons),
    }
    data.update(kwargs)
    return AirspaceFeature.objects.create(**data)


def seed_google():
    """P901 about 111 m off on one vertex, R903 a circle ~1 % bigger, R904 as a point, plus a
    zone and a naval zone that the AIP does not have."""
    snap = google_snapshot()
    square = [[-70.0, -30.001], [-69.0, -30.0], [-69.0, -31.0], [-70.0, -31.0]]
    google_feature(snap, "g1", "SC-P901", "prohibited", square + [square[0]])
    circle = aip_parser.circle_ring(-34.0, -70.5, 1852 * 1.01)
    google_feature(snap, "g3", "SC-R903", "restricted", circle)
    google_feature(snap, "g4", "SC-R904", "restricted")
    google_feature(snap, "g5", "SC-P977", "prohibited", square + [square[0]])
    google_feature(snap, "g6", "", "naval")
    google_feature(snap, "g7", "SCXA", "aerodrome")
    return snap


# ── the amendment ───────────────────────────────────────────────────────────


def test_the_amendment_is_the_highest_number_with_its_date():
    pages = make_pages([ZONE_P901], amdt=44, date="08 DEC 2016") + make_pages(
        [ZONE_P901], amdt=67, date="06 AUG 2026"
    )
    pages += make_pages([ZONE_P901], amdt=49, date="13 AUG 2020")
    assert aip_parser.extract_amendment(pages) == ("67", datetime.date(2026, 8, 6))


def test_spanish_month_abbreviations_are_read_and_no_amendment_is_not_invented():
    pages = make_pages([ZONE_P901], amdt=68, date="26 NOV 2026")
    assert aip_parser.extract_amendment(pages)[1] == datetime.date(2026, 11, 26)
    assert aip_parser.extract_amendment(
        make_pages([ZONE_P901], date="05 DIC 2026")
    ) == ("67", datetime.date(2026, 12, 5))
    assert aip_parser.extract_amendment([_row("sin enmienda", 85, 10)]) == ("", None)


def test_zones_carry_the_page_they_start_on():
    zones, _ = aip_parser.parse_enr51_words(make_pages(BASE_ZONES))
    assert {z["page"] for z in zones} == {1}


# ── happy path ──────────────────────────────────────────────────────────────


def test_import_creates_a_draft_snapshot_with_its_zones(tmp_path, words):
    out = run(file=str(pdf_file(tmp_path)))
    snapshot = aip_snapshots().get()
    assert snapshot.status == "draft" and snapshot.is_current is False
    assert snapshot.amdt_number == "67"
    assert snapshot.effective_date == datetime.date(2026, 8, 6)
    assert len(snapshot.pdf_sha256) == 64 and snapshot.sha256 == snapshot.pdf_sha256
    assert snapshot.feature_count == 4
    assert snapshot.attribution == (
        "Fuente: AIP-Chile, DGAC, AMDT NR 67 (06 AUG 2026), ENR 5.1. "
        "Referencial; consulte NOTAM/SUP vigentes."
    )
    assert "Added a draft snapshot: AMDT 67" in out and "Nothing is published" in out

    by_code = {f.code: f for f in aip_features()}
    assert set(by_code) == {"SC-P901", "SC-P902", "SC-R903", "SC-R904"}
    clean = by_code["SC-P901"]
    assert clean.kind == "prohibited" and clean.geometry_method == "polygon"
    assert clean.review_status == "pending" and clean.parse_warnings == []
    assert clean.is_active is False and clean.snapshot == snapshot
    assert clean.folder == "ENR 5.1-1" and clean.vertical_limits_text == "UNL / GND"
    assert clean.lateral_text.startswith("área definida")
    assert clean.geometry["type"] == "Polygon" and clean.min_lat == -31.0

    bowtie = by_code["SC-P902"]
    assert bowtie.review_status == "needs_review"
    assert any(w.startswith("bowtie") for w in bowtie.parse_warnings)

    circle = by_code["SC-R903"]
    assert circle.geometry_method == "circle" and circle.vertical_limits_text == (
        "FL 100 / GND"
    )

    arc = by_code["SC-R904"]
    assert arc.geometry_method == "arc" and arc.review_status == "needs_review"
    assert arc.geometry == aip_import.EMPTY_GEOMETRY
    assert any(w.startswith("external_centre") for w in arc.parse_warnings)


def test_the_report_names_kinds_and_warnings(tmp_path, words):
    out = run(file=str(pdf_file(tmp_path)))
    assert "4 zones; 4 new, 0 changed, 0 unchanged" in out
    assert "by kind: {'P': 2, 'R': 2}" in out
    assert "bowtie" in out and "external_centre" in out
    assert "no current Google snapshot" in out


# ── idempotence, dry run and failures ───────────────────────────────────────


def test_the_same_pdf_twice_changes_nothing(tmp_path, words):
    path = pdf_file(tmp_path)
    run(file=str(path))
    features, checks = aip_features().count(), AirspaceCrossCheck.objects.count()
    out = run(file=str(path))
    assert "No changes" in out and "AMDT 67" in out
    assert aip_snapshots().count() == 1
    assert aip_features().count() == features
    assert AirspaceCrossCheck.objects.count() == checks


def test_dry_run_reports_and_writes_nothing(tmp_path, words):
    seed_google()
    snapshots, checks = (
        AirspaceSnapshot.objects.count(),
        AirspaceCrossCheck.objects.count(),
    )
    out = run(file=str(pdf_file(tmp_path)), dry_run=True)
    assert "Would add a draft snapshot" in out and "Dry run: nothing was written" in out
    assert "missing_in_aip" in out
    assert AirspaceSnapshot.objects.count() == snapshots
    assert AirspaceFeature.objects.filter(source_kind="aip_enr51").count() == 0
    assert AirspaceCrossCheck.objects.count() == checks


def test_a_missing_file_is_a_clear_error(tmp_path, words):
    with pytest.raises(CommandError, match="Cannot read"):
        run(file=str(tmp_path / "no-such.pdf"))
    assert aip_snapshots().count() == 0


def test_bytes_that_are_not_a_pdf_are_refused(tmp_path, words):
    path = tmp_path / "x.pdf"
    path.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(CommandError, match="not a PDF"):
        run(file=str(path))
    assert aip_snapshots().count() == 0


def test_an_unreadable_pdf_is_a_clear_error(tmp_path, words):
    words["pages"] = aip_pdf.PdfUnreadable("The file is not a readable PDF (X).")
    with pytest.raises(CommandError, match="not a readable PDF"):
        run(file=str(pdf_file(tmp_path)))
    assert aip_snapshots().count() == 0


def test_a_missing_pdf_library_says_how_to_install_it(tmp_path, words):
    words["pages"] = aip_pdf.PdfSupportMissing("no pdfplumber")
    with pytest.raises(CommandError, match="pdfplumber"):
        run(file=str(pdf_file(tmp_path)))


def test_a_pdf_without_zones_writes_nothing(tmp_path, words):
    words["pages"] = [_row("AIP-CHILE ENR 5.1-1 un texto cualquiera", 85, 26)]
    with pytest.raises(CommandError, match="No zones were found"):
        run(file=str(pdf_file(tmp_path)))
    assert aip_snapshots().count() == 0


def test_exactly_one_of_file_or_url_is_required(words):
    with pytest.raises(CommandError, match="exactly one"):
        run()
    with pytest.raises(CommandError, match="exactly one"):
        run(file="a.pdf", url="https://x.test/a.pdf")


def test_the_default_url_is_the_aips_enr51_file():
    assert aip_import.DEFAULT_URL == (
        "https://aipchile.dgac.gob.cl/dasa/aip_chile_con_contenido/ais/"
        "2%20ENR%20Parte%202/"
        "ENR%205%20Zonas%20Prohibidas%2C%20Restringidas%20y%20Peligrosas/"
        "ENR%205.1-1%20Zonas%20P%2C%20R%2C%20D.pdf"
    )


def test_url_without_value_downloads_the_default(monkeypatch, words):
    seen = {}

    def fake_fetch(url, timeout):
        seen.update(url=url, timeout=timeout)
        return b"%PDF-1.4 downloaded"

    monkeypatch.setattr(aip_import, "fetch_pdf", fake_fetch)
    out = run(url=aip_import.DEFAULT_URL, timeout=7)
    assert seen == {"url": aip_import.DEFAULT_URL, "timeout": 7}
    assert aip_snapshots().get().source_url == aip_import.DEFAULT_URL
    assert "Added a draft snapshot" in out


def test_a_failed_download_touches_nothing(monkeypatch, tmp_path, words):
    run(file=str(pdf_file(tmp_path)))

    def boom(url, timeout=30):
        raise aip_import.kml_import.AirspaceFetchError(
            "The source did not answer (URLError). The current snapshot was not touched."
        )

    monkeypatch.setattr(aip_import.kml_import, "fetch_url", boom)
    with pytest.raises(CommandError, match="did not answer"):
        run(url="https://aip.test/enr51.pdf")
    assert aip_snapshots().count() == 1


def test_the_download_is_a_function_of_the_command_only():
    """Serving a page never reaches the network: only the command module and `aip_import` do."""
    import pathlib

    root = pathlib.Path(aip_import.__file__).parent
    for name in ("views.py", "payload.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "fetch_url" not in text and "urlopen" not in text


# ── nothing is published by itself ──────────────────────────────────────────


def test_nothing_is_drawn_until_it_is_approved(tmp_path, words):
    google = seed_google()
    before = [f.pk for f in payload.active_features()]
    run(file=str(pdf_file(tmp_path)))
    assert payload.current_snapshot() == google
    assert [f.pk for f in payload.active_features()] == before
    assert not payload.active_features().filter(source_kind="aip_enr51").exists()
    served = payload.build_payload(google)
    assert not [
        f
        for f in served["features"]
        if f["code"] in {"SC-P901", "SC-R903"} and f["name"].startswith("Zona")
    ]
    assert not AirspaceSnapshot.objects.filter(
        source_kind="aip_enr51", is_current=True
    ).exists()


# ── a newer PDF ─────────────────────────────────────────────────────────────


def publish_first_snapshot():
    """What phase 4 does: the snapshot becomes the current one, its zones approved and active."""
    snapshot = aip_snapshots().get()
    user = get_user_model().objects.create_user("reviewer", password="pw-test-1234")
    aip_features().update(
        is_active=True,
        review_status="approved",
        reviewed_by=user,
        reviewed_at=timezone.now(),
    )
    snapshot.status, snapshot.is_current = "published", True
    snapshot.save()
    return snapshot, user


def test_a_new_pdf_makes_a_new_snapshot_and_leaves_the_current_one_alone(
    tmp_path, words
):
    run(file=str(pdf_file(tmp_path, "a")))
    first, _user = publish_first_snapshot()

    changed = dict(
        ZONE_P901, col3=["H24"], col1=[*ZONE_P901["col1"][:-1], "31 00 00 S 70 00 30 W"]
    )
    words["pages"] = make_pages(
        [changed, ZONE_P902, ZONE_R903], amdt=68, date="26 NOV 2026"
    )
    out = run(file=str(pdf_file(tmp_path, "b")))

    second = aip_snapshots().exclude(pk=first.pk).get()
    assert second.status == "draft" and second.amdt_number == "68"
    assert (second.added, second.changed, second.archived) == (0, 1, 1)
    assert (
        "1 changed, 2 unchanged, 1 to archive" in out and "to archive: SC-R904" in out
    )

    first.refresh_from_db()
    assert first.is_current and first.status == "published"
    # The published rows are untouched until the new one is published.
    assert aip_features().filter(snapshot=first, is_active=True).count() == 4
    assert aip_features().filter(snapshot=second, is_active=True).count() == 0


def test_an_unchanged_zone_keeps_the_decision_and_the_correction_of_a_person(
    tmp_path, words
):
    run(file=str(pdf_file(tmp_path, "a")))
    first, user = publish_first_snapshot()
    corrected = aip_features().get(code="SC-P902")
    corrected.geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [-70.0, -30.0],
                [-69.0, -30.0],
                [-69.0, -31.0],
                [-70.0, -31.0],
                [-70.0, -30.0],
            ]
        ],
    }
    corrected.save()

    words["pages"] = make_pages(BASE_ZONES, amdt=68, date="26 NOV 2026")
    run(file=str(pdf_file(tmp_path, "b")))
    second = aip_snapshots().exclude(pk=first.pk).get()
    carried = aip_features().get(snapshot=second, code="SC-P902")
    assert carried.review_status == "approved" and carried.reviewed_by == user
    assert (
        carried.geometry == corrected.geometry and carried.geometry_method == "polygon"
    )
    assert carried.min_lat == -31.0
    assert (second.added, second.changed, second.archived) == (0, 0, 0)


def test_a_changed_zone_starts_pending_again(tmp_path, words):
    run(file=str(pdf_file(tmp_path, "a")))
    first, _ = publish_first_snapshot()
    changed = dict(ZONE_P901, col1=[*ZONE_P901["col1"][:-1], "31 00 00 S 70 00 30 W"])
    words["pages"] = make_pages([changed, ZONE_P902, ZONE_R903, ZONE_R904])
    run(file=str(pdf_file(tmp_path, "b")))
    row = aip_features().get(code="SC-P901", is_active=False)
    assert row.review_status == "pending" and row.reviewed_by is None


def test_a_newer_pdf_closes_the_unpublished_snapshot_it_replaces(tmp_path, words):
    run(file=str(pdf_file(tmp_path, "a")))
    old = aip_snapshots().get()
    words["pages"] = make_pages(BASE_ZONES[:3], amdt=68, date="26 NOV 2026")
    out = run(file=str(pdf_file(tmp_path, "b")))
    new = aip_snapshots().exclude(pk=old.pk).get()
    old.refresh_from_db()
    assert old.status == "rejected" and new.status == "draft"
    assert aip_features().filter(snapshot=old).count() == 4  # nothing is deleted
    assert all(f.archived_in == new for f in aip_features().filter(snapshot=old))
    assert "1 earlier unpublished snapshot" in out
    # Re-importing the first PDF is not "no changes": the latest one is another file.
    words["pages"] = make_pages(BASE_ZONES)
    assert "Added a draft snapshot" in run(file=str(pdf_file(tmp_path, "a")))


# ── cross-check ─────────────────────────────────────────────────────────────


def results():
    return {
        (c.code, c.result): c
        for c in AirspaceCrossCheck.objects.select_related(
            "aip_feature", "google_feature"
        )
    }


def test_the_cross_check_measures_distances_without_judging_by_default(
    tmp_path, words, settings
):
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = None
    snap = seed_google()
    out = run(file=str(pdf_file(tmp_path)))
    rows = results()
    assert set(rows) == {
        ("SC-P901", "measured"),
        ("SC-P902", "missing_in_google"),
        ("SC-R903", "measured"),
        ("SC-R904", "measured"),
        ("SC-P977", "missing_in_aip"),
        ("", "google_only"),
    }
    p901 = rows[("SC-P901", "measured")]
    assert 100 < p901.max_vertex_m < 125 and p901.median_m < p901.max_vertex_m
    assert p901.aip_feature.code == "SC-P901" and p901.google_feature.code == "SC-P901"
    r903 = rows[("SC-R903", "measured")]
    assert 5 < r903.max_vertex_m < 40
    arc = rows[("SC-R904", "measured")]
    assert (
        arc.max_vertex_m is None and arc.median_m is None
    )  # nothing to measure, nothing invented
    assert rows[("SC-P902", "missing_in_google")].google_feature is None
    assert rows[("SC-P977", "missing_in_aip")].aip_feature is None
    assert all(
        c.snapshot == aip_snapshots().get() for c in AirspaceCrossCheck.objects.all()
    )
    assert "no threshold set" in out and "'measured': 3" in out
    # The aerodrome of the Google map is not a zone: it is not compared.
    assert not AirspaceCrossCheck.objects.filter(
        google_feature__kind="aerodrome"
    ).exists()
    # The Google rows are untouched.
    snap.refresh_from_db()
    assert snap.is_current and snap.status == "published"


def test_with_a_threshold_the_result_is_match_or_discrepancy(tmp_path, words, settings):
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = 50.0
    seed_google()
    run(file=str(pdf_file(tmp_path)))
    rows = results()
    assert ("SC-P901", "discrepancy") in rows  # ~111 m > 50 m
    assert ("SC-R903", "match") in rows  # a few metres
    assert ("SC-R904", "measured") in rows  # cannot be judged without geometry


def test_a_larger_threshold_turns_the_same_distance_into_a_match(
    tmp_path, words, settings
):
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = 500.0
    seed_google()
    run(file=str(pdf_file(tmp_path)))
    assert ("SC-P901", "match") in results()


def test_without_a_google_snapshot_there_is_nothing_to_compare(tmp_path, words):
    run(file=str(pdf_file(tmp_path)))
    assert AirspaceCrossCheck.objects.count() == 0


def test_the_threshold_setting_is_blank_by_default(settings):
    from django.conf import settings as live

    assert live.AIRSPACE_CROSSCHECK_THRESHOLD_M is None


def test_the_crosscheck_function_is_pure_and_picks_the_closest_duplicate():
    snap = google_snapshot()
    far = [
        [-70.0, -30.1],
        [-69.0, -30.1],
        [-69.0, -31.1],
        [-70.0, -31.1],
        [-70.0, -30.1],
    ]
    near = [
        [-70.0, -30.0],
        [-69.0, -30.0],
        [-69.0, -31.0],
        [-70.0, -31.0],
        [-70.0, -30.0],
    ]
    google_feature(snap, "a", "SC-P901", "prohibited", far)
    good = google_feature(snap, "b", "SC-P901", "prohibited", near)
    row = aip_import.ZoneRow(
        "k",
        "h",
        "prohibited",
        "SC-P901",
        "n",
        "",
        "",
        "",
        "",
        {"type": "Polygon", "coordinates": [near]},
        "polygon",
        [],
        "pending",
    )
    (item,) = aip_import.compare([row], aip_import.google_reference())
    assert item.google == good and item.max_vertex_m == 0.0


# ── personal data ───────────────────────────────────────────────────────────


def test_no_contact_survives_anywhere_in_the_database(tmp_path, words):
    seed_google()
    assert all(s in REMARKS_WITH_CONTACTS for s in SENTINELS)
    run(file=str(pdf_file(tmp_path)))
    run(file=str(pdf_file(tmp_path)), dry_run=True)
    assert (
        aip_import.aip_parser.CONTACT_PLACEHOLDER
        in aip_features().get(code="SC-P901").schedule_text
    )
    dump = "\n".join(connection.connection.iterdump())
    for needle in SENTINELS:
        assert needle not in dump, needle
    # What was kept of the remarks is the schedule, not the contact.
    assert "0800-1700 LT" in aip_features().get(code="SC-P901").schedule_text


# ── the real PDF layer (optional dependency) ────────────────────────────────


def test_a_real_synthetic_pdf_goes_through_the_command(tmp_path):
    pytest.importorskip("pdfplumber")
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    path = tmp_path / "synthetic.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    pdf.drawString(85, 792 - 26, "AIP-CHILE ENR 5.1-9")
    pdf.drawString(85, 792 - 37, "VOLUMEN I 06 AUG 2026")
    pdf.drawString(85, 792 - 700, "AIS - CHILE AMDT NR 67")
    for x, label in ((173, "1"), (324, "2"), (455, "3")):
        pdf.drawString(x, 792 - 60, label)
    pdf.drawString(85, 792 - 100, "SC-P901 FIR SANTIAGO")
    pdf.drawString(85, 792 - 112, "Zona Sintetica Uno")
    pdf.drawString(85, 792 - 124, INTRO)
    for i, vertex in enumerate(SQUARE):
        pdf.drawString(85, 792 - 136 - 12 * i, vertex)
    pdf.drawString(300, 792 - 136, "UNL")
    pdf.drawString(300, 792 - 148, "GND")
    pdf.drawString(393, 792 - 136, "H24 centinela.uno@test.com")
    pdf.save()
    out = run(file=str(path))
    feature = aip_features().get()
    assert feature.code == "SC-P901" and feature.geometry_method == "polygon"
    assert aip_snapshots().get().amdt_number == "67"
    assert "centinela" not in feature.schedule_text and "H24" in feature.schedule_text
    assert "Added a draft snapshot" in out


def test_a_garbage_pdf_is_unreadable_through_the_real_layer(tmp_path):
    pytest.importorskip("pdfplumber")
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"%PDF-1.4 this is not really a pdf at all")
    with pytest.raises(CommandError, match="not a readable PDF"):
        run(file=str(path))
    assert aip_snapshots().count() == 0


def test_parse_pdf_reads_from_memory_not_from_a_path(words):
    parsed = aip_import.parse_pdf(b"%PDF-1.4 mem")
    assert len(parsed.zones) == 4 and parsed.amdt_number == "67"


# ── the new constraint values ───────────────────────────────────────────────


def test_measured_needs_both_features_and_snapshot_is_optional():
    from django.db import IntegrityError, transaction

    snap = google_snapshot()
    one = google_feature(snap, "m1", "SC-P1", "prohibited")
    two = google_feature(snap, "m2", "SC-P1", "prohibited")
    AirspaceCrossCheck.objects.create(
        code="SC-P1", aip_feature=one, google_feature=two, result="measured"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(
            code="SC-P1", aip_feature=one, result="measured"
        )
