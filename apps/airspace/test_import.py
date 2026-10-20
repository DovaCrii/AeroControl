"""LV-357 fase 1: importar el mapa de espacio aéreo, con un KML SINTÉTICO.

Los datos reales no van a git (licencia sin confirmar, repositorio público): el
archivo de `test_data/` tiene lugares inventados con las mismas rarezas que la
fuente (códigos mal escritos, círculos como LineString cerrado, un `<script>` en
una descripción, ayudas de dibujo, una carpeta vacía).
"""

import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from apps.airspace import kml_import
from apps.airspace.models import AirspaceFeature, AirspaceSnapshot
from apps.geo.kml.errors import KmlImportError

SYNTHETIC = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"


@pytest.fixture
def kml_bytes():
    return SYNTHETIC.read_bytes()


@pytest.fixture
def kml_file(tmp_path, kml_bytes):
    path = tmp_path / "map.kml"
    path.write_bytes(kml_bytes)
    return path


def run(*args):
    out = io.StringIO()
    call_command("import_airspace_zones", *args, stdout=out)
    return out.getvalue()


def by_name(result, fragment):
    matches = [f for f in result.features if fragment in f.name]
    assert len(matches) == 1, fragment
    return matches[0]


# ── códigos ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("SC-P29", "SC-P29"),
        ("SC - R54 FIR ANTOFAGASTA", "SC-R54"),
        ("SC R-41", "SC-R41"),
        ("SC – P 30", "SC-P30"),
        ("SC—D66 Calama", "SC-D66"),
        ("ZONA RESTRINGIDA SC R74 ", "SC-R74"),
        ("SC P83 IV DIV EJERCITO", "SC-P83"),
        ("Zona Prohibida SC- P55 instalaciones", "SC-P55"),
        ("SC-P05", "SC-P5"),
        ("SCEL Ap Arturo Merino", ""),
        ("MISC-R12 algo", ""),
        ("SC-X12", ""),
        ("SC-P1234", ""),
        ("PALACIO PEREIRA", ""),
        ("", ""),
    ],
)
def test_zone_code_normalization(text, expected):
    assert kml_import.normalize_zone_code(text) == expected


# ── texto ───────────────────────────────────────────────────────────────────


def test_html_becomes_plain_text_and_scripts_are_dropped():
    text = kml_import.html_to_text(
        'A<br>B <script>alert("x")</script><b>c</b> &amp; d<style>p{}</style>'
        "<img src=x onerror=alert(1)>"
    )
    assert text == "A\nB c & d"
    assert "<" not in text and "alert" not in text


def test_empty_my_maps_columns_are_not_kept_as_text():
    assert kml_import.html_to_text("descripción: <br>tracking_href_2: ") == ""


def test_limits_are_copied_as_the_source_wrote_them():
    vertical, schedule = kml_import.extract_limits(
        "Límites Verticales:\n1000 FT AGL\nHORARIO:\n\nPermanente\nCoordinación x"
    )
    assert vertical == "Límites Verticales: / 1000 FT AGL"
    assert schedule == "HORARIO: / Permanente"


# ── parseo del KML sintético ────────────────────────────────────────────────


def test_synthetic_kml_is_classified(kml_bytes):
    result = kml_import.parse_airspace_kml(kml_bytes)
    kinds = {f.name: f.kind for f in result.features}
    assert result.document_name == "MAPA SINTETICO"
    assert len(result.features) == 13
    assert kinds["SCXA Ad. Prueba Uno SANTIAGO"] == "aerodrome"
    assert kinds["SCXB Ap. Prueba Dos VALPARAISO"] == "airport"
    assert kinds["Pista Inventada (SCXC)"] == "airstrip"
    assert by_name(result, "R54").kind == "restricted"
    assert by_name(result, "P 30").kind == "prohibited"
    assert by_name(result, "R-41").kind == "restricted"
    assert by_name(result, "D66").kind == "danger"
    assert by_name(result, "PRIMERA ZONA NAVAL").kind == "naval"
    assert by_name(result, "Limite Norte").kind == "fir_boundary"
    assert kinds["Punto centrado Muelle Ficticio"] == "aux"
    assert kinds["Medida de círculo"] == "aux"


def test_codes_are_normalized_and_oaci_is_read(kml_bytes):
    result = kml_import.parse_airspace_kml(kml_bytes)
    assert by_name(result, "R54").code == "SC-R54"
    assert by_name(result, "P 30").code == "SC-P30"
    assert by_name(result, "R-41").code == "SC-R41"
    assert by_name(result, "SCXA").code == "SCXA"
    assert by_name(result, "SCXC").code == "SCXC"
    assert by_name(result, "Ad. Sin Codigo").code == ""


def test_a_closed_linestring_circle_becomes_a_polygon(kml_bytes):
    result = kml_import.parse_airspace_kml(kml_bytes)
    circle = by_name(result, "P 30")
    assert circle.geometry["type"] == "Polygon"
    ring = circle.geometry["coordinates"][0]
    assert len(ring) == 73 and ring[0] == ring[-1]
    assert "1 closed line(s) converted to polygons" in " ".join(result.warnings)
    # una línea abierta (límite de FIR) sigue siendo línea
    assert by_name(result, "Limite Norte").geometry["type"] == "LineString"


def test_script_in_a_description_never_reaches_the_text(kml_bytes):
    zone = by_name(kml_import.parse_airspace_kml(kml_bytes), "R54")
    assert "<" not in zone.description_text
    assert "alert" not in zone.description_text
    assert "negrita & fin." in zone.description_text
    assert "9000 FT AMSL" in zone.vertical_limits_text
    assert "H24" in zone.schedule_text
    assert "\n" not in zone.name


def test_quality_warnings_name_what_the_source_got_wrong(kml_bytes):
    warnings = " | ".join(kml_import.parse_airspace_kml(kml_bytes).warnings)
    assert "aerodrome without an ICAO code: 'Ad. Sin Codigo'" in warnings
    assert "zone without a code kept as a drawing aid: 'ZONA SIN CODIGO'" in warnings


def test_bounding_box_and_center(kml_bytes):
    zone = by_name(kml_import.parse_airspace_kml(kml_bytes), "R54")
    assert (zone.min_lat, zone.max_lat) == (-33.62, -33.5)
    assert (zone.min_lon, zone.max_lon) == (-70.72, -70.66)
    point = by_name(kml_import.parse_airspace_kml(kml_bytes), "SCXA")
    assert (point.center_lat, point.center_lon) == (-33.5, -70.7)


def test_doctype_is_rejected(kml_bytes):
    hostile = b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "b">]>' + kml_bytes
    with pytest.raises(KmlImportError):
        kml_import.parse_airspace_kml(hostile)


@pytest.mark.parametrize(
    "data",
    [b"", b"not xml", b"<kml><Document></Document></kml>"],
)
def test_unusable_files_raise(data):
    with pytest.raises(KmlImportError):
        kml_import.parse_airspace_kml(data)


def test_placemark_with_bad_coordinates_is_skipped_with_a_warning():
    data = (
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>'
        b"<name>AERODROMOS</name>"
        b"<Placemark><name>SCZZ Ad. Fuera</name>"
        b"<Point><coordinates>-70.0,-95.0,0</coordinates></Point></Placemark>"
        b"<Placemark><name>SCZY Ad. Bien</name>"
        b"<Point><coordinates>-70.0,-33.0,0</coordinates></Point></Placemark>"
        b"</Folder></Document></kml>"
    )
    result = kml_import.parse_airspace_kml(data)
    assert [f.code for f in result.features] == ["SCZY"]
    assert any("Fuera" in w for w in result.warnings)


def test_duplicate_names_get_distinct_keys_and_a_warning():
    data = (
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>'
        b"<name>Pistas chicas</name>"
        b"<Placemark><name>Pista Igual</name>"
        b"<Point><coordinates>-70.0,-33.0,0</coordinates></Point></Placemark>"
        b"<Placemark><name>Pista Igual</name>"
        b"<Point><coordinates>-70.1,-33.0,0</coordinates></Point></Placemark>"
        b"</Folder></Document></kml>"
    )
    result = kml_import.parse_airspace_kml(data)
    assert len({f.source_key for f in result.features}) == 2
    assert any("duplicate" in w for w in result.warnings)


# ── comando ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_import_happy_path(kml_file):
    output = run("--file", str(kml_file))
    assert "Added 13, changed 0, archived 0" in output
    snapshot = AirspaceSnapshot.objects.get()
    assert snapshot.is_current and snapshot.feature_count == 13
    assert snapshot.added == 13
    assert snapshot.source_url == "map.kml"  # sólo el nombre, nunca la ruta
    assert "DGAC" in snapshot.attribution
    assert AirspaceFeature.objects.filter(is_active=True).count() == 13
    assert AirspaceFeature.objects.filter(snapshot=snapshot).count() == 13


@pytest.mark.django_db
def test_point_features_get_region_and_commune(kml_file):
    run("--file", str(kml_file))
    aerodrome = AirspaceFeature.objects.get(code="SCXA")
    assert aerodrome.region
    zone = AirspaceFeature.objects.get(code="SC-R54")
    assert zone.region == "" and zone.commune == ""


@pytest.mark.django_db
def test_second_run_with_the_same_file_does_nothing(kml_file):
    run("--file", str(kml_file))
    output = run("--file", str(kml_file))
    assert "No changes" in output
    assert AirspaceSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_a_moved_geometry_is_changed_not_added_and_keeps_history(kml_file):
    run("--file", str(kml_file))
    kml_file.write_text(
        kml_file.read_text(encoding="utf-8").replace(
            "-70.700000,-33.500000,0", "-70.710000,-33.510000,0"
        ),
        encoding="utf-8",
    )
    output = run("--file", str(kml_file))
    assert "Added 0, changed 1, archived 0" in output
    assert AirspaceSnapshot.objects.filter(is_current=True).count() == 1
    assert AirspaceSnapshot.objects.count() == 2
    latest = AirspaceSnapshot.objects.get(is_current=True)
    assert (latest.added, latest.changed, latest.archived) == (0, 1, 0)
    rows = AirspaceFeature.objects.filter(code="SCXA")
    assert rows.count() == 2  # la versión vieja queda archivada, no se pisa
    assert rows.get(is_active=True).center_lon == -70.71
    old = rows.get(is_active=False)
    assert old.center_lon == -70.7 and old.archived_in == latest


@pytest.mark.django_db
def test_a_changed_description_is_detected(kml_file):
    run("--file", str(kml_file))
    kml_file.write_text(
        kml_file.read_text(encoding="utf-8").replace(
            "Coordinación con Torre Ficticia", "Coordinación con Otra Torre"
        ),
        encoding="utf-8",
    )
    assert "changed 1" in run("--file", str(kml_file))


@pytest.mark.django_db
def test_a_feature_that_disappears_is_archived_never_deleted(kml_file):
    run("--file", str(kml_file))
    text = kml_file.read_text(encoding="utf-8")
    start = text.index("<Placemark>\n        <name>SC-D66")
    end = text.index("</Placemark>", start) + len("</Placemark>")
    kml_file.write_text(text[:start] + text[end:], encoding="utf-8")
    output = run("--file", str(kml_file))
    assert "Added 0, changed 0, archived 1" in output
    assert "archived: SC-D66" in output
    gone = AirspaceFeature.objects.get(code="SC-D66")
    assert gone.is_active is False
    assert gone.archived_in == AirspaceSnapshot.objects.get(is_current=True)
    assert AirspaceFeature.objects.count() == 13


@pytest.mark.django_db
def test_a_reappearing_feature_is_added_again(kml_file):
    original = kml_file.read_text(encoding="utf-8")
    run("--file", str(kml_file))
    start = original.index("<Placemark>\n        <name>SC-D66")
    end = original.index("</Placemark>", start) + len("</Placemark>")
    kml_file.write_text(original[:start] + original[end:], encoding="utf-8")
    run("--file", str(kml_file))
    kml_file.write_text(original, encoding="utf-8")
    assert "Added 1, changed 0, archived 0" in run("--file", str(kml_file))
    assert AirspaceFeature.objects.filter(code="SC-D66", is_active=True).count() == 1


@pytest.mark.django_db
def test_dry_run_reports_and_writes_nothing(kml_file):
    output = run("--file", str(kml_file), "--dry-run")
    assert "Would add 13" in output and "Dry run" in output
    assert AirspaceSnapshot.objects.count() == 0
    assert AirspaceFeature.objects.count() == 0


@pytest.mark.django_db
def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(CommandError, match="Cannot read"):
        run("--file", str(tmp_path / "nope.kml"))
    assert AirspaceSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_malformed_file_is_a_clear_error_and_keeps_the_current_snapshot(
    kml_file, tmp_path
):
    run("--file", str(kml_file))
    bad = tmp_path / "bad.kml"
    bad.write_bytes(b"<kml><oops>")
    with pytest.raises(CommandError, match="Not a usable KML"):
        run("--file", str(bad))
    assert AirspaceSnapshot.objects.get().is_current
    assert AirspaceFeature.objects.filter(is_active=True).count() == 13


@pytest.mark.django_db
def test_exactly_one_source_is_required(kml_file):
    with pytest.raises(CommandError, match="exactly one"):
        run()
    with pytest.raises(CommandError, match="exactly one"):
        run("--file", str(kml_file), "--url", "https://example.invalid/x.kml")


@pytest.mark.django_db
def test_download_failure_does_not_touch_the_current_snapshot(kml_file, monkeypatch):
    run("--file", str(kml_file))

    def boom(url, timeout):
        raise kml_import.AirspaceFetchError("The source did not answer (URLError).")

    monkeypatch.setattr(kml_import, "fetch_url", boom)
    with pytest.raises(CommandError, match="did not answer"):
        run("--url", "https://example.invalid/x.kml")
    assert AirspaceSnapshot.objects.get().is_current
    assert AirspaceFeature.objects.filter(is_active=True).count() == 13


@pytest.mark.django_db
def test_url_import_records_the_url(kml_bytes, monkeypatch):
    monkeypatch.setattr(kml_import, "fetch_url", lambda url, timeout: kml_bytes)
    run("--url", "https://example.invalid/x.kml")
    assert AirspaceSnapshot.objects.get().source_url == "https://example.invalid/x.kml"


@pytest.mark.django_db
def test_bare_url_flag_uses_the_default_map(kml_bytes, monkeypatch):
    seen = []

    def fake(url, timeout):
        seen.append(url)
        return kml_bytes

    monkeypatch.setattr(kml_import, "fetch_url", fake)
    run("--url")
    assert seen == [kml_import.DEFAULT_URL]


def test_fetch_rejects_non_http_schemes():
    with pytest.raises(kml_import.AirspaceFetchError):
        kml_import.fetch_url("file:///etc/passwd")


@pytest.mark.parametrize("error", [urllib.error.URLError("down"), TimeoutError()])
def test_fetch_turns_network_errors_into_a_clear_one(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(kml_import.AirspaceFetchError, match="did not answer"):
        kml_import.fetch_url("https://example.invalid/x.kml", timeout=1)


def test_fetch_rejects_an_oversized_answer(monkeypatch):
    class Big:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return b"x" * n

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Big())
    with pytest.raises(kml_import.AirspaceFetchError, match="larger"):
        kml_import.fetch_url("https://example.invalid/x.kml")


# ── modelo, admin y permisos ────────────────────────────────────────────────


@pytest.mark.django_db
def test_only_one_snapshot_can_be_current(kml_file):
    run("--file", str(kml_file))
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceSnapshot.objects.create(
            source_name="x",
            fetched_at=AirspaceSnapshot.objects.get().fetched_at,
            sha256="0" * 64,
            attribution="x",
            is_current=True,
        )


@pytest.mark.django_db
def test_an_active_source_key_is_unique_but_archived_ones_may_repeat(kml_file):
    run("--file", str(kml_file))
    row = AirspaceFeature.objects.filter(is_active=True).first()
    clone = AirspaceFeature.objects.get(pk=row.pk)
    clone.pk = None
    clone.id = None
    with pytest.raises(IntegrityError), transaction.atomic():
        clone.save(force_insert=True)


@pytest.mark.django_db
def test_bbox_must_be_ordered(kml_file):
    run("--file", str(kml_file))
    row = AirspaceFeature.objects.filter(is_active=True).first()
    row.min_lat, row.max_lat = 10, -10
    with pytest.raises(IntegrityError), transaction.atomic():
        row.save()


@pytest.mark.django_db
def test_unknown_kind_is_rejected_by_the_database(kml_file):
    run("--file", str(kml_file))
    row = AirspaceFeature.objects.filter(is_active=True).first()
    row.kind = "mystery"
    with pytest.raises(IntegrityError), transaction.atomic():
        row.save()


@pytest.mark.django_db
def test_admin_is_read_only(rf, django_user_model):
    user = django_user_model.objects.create_superuser("root", "r@example.invalid", "x")
    request = rf.get("/")
    request.user = user
    for model in (AirspaceSnapshot, AirspaceFeature):
        model_admin = admin.site._registry[model]
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_operations_can_view_the_catalog_and_viewer_cannot():
    call_command("bootstrap_roles")
    codenames = lambda name: set(  # noqa: E731
        Group.objects.get(name=name).permissions.values_list("codename", flat=True)
    )
    assert "view_airspacefeature" in codenames("Operations")
    assert "view_airspacefeature" not in codenames("Viewer")
    # sólo lectura: el catálogo se escribe con el comando
    for role in ("Operations", "Compliance", "Viewer"):
        assert not {c for c in codenames(role) if c.endswith("airspacefeature")} - {
            "view_airspacefeature"
        }
