"""LV-427 (fase 1): lector de logs de vuelo — estructura, análisis automático y pantalla con mapa.

El parser DJI real no está conectado: el adaptador DJI es un stub y todo lo que se ve acá sale del
adaptador **sintético** (coordenadas inventadas, ver `fixtures_lv427/`).
"""

import io
import json
import re
from datetime import time, timedelta
from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.testing import login_as
from apps.operations.flightlog import FlightLogError, parse_flight_log
from apps.operations.flightlog.types import FlightTrack, TrackPoint
from apps.operations.models import (
    FlightLogAnalysis,
    FlightPermission,
    FlightRecord,
)
from apps.registry.models import Aircraft, CostCenter, Operator

FIXTURE = Path(__file__).parent / "fixtures_lv427" / "synthetic_flight.json"
ROOT = Path(__file__).resolve().parents[2]
TODAY = timezone.localdate()
READ = ("view_flightpermission", "view_flightrecord")


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    settings.DOCUMENTS_ROOT = tmp_path / "docs"
    settings.DOCUMENTS_ROOT.mkdir()


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(
        code="CC900", name="Faena X", operates_flights=True
    )


@pytest.fixture
def permit(centre):
    aircraft = Aircraft.objects.create(
        registration="RPA-9001",
        serial_number="SN-9001",
        type="RPA",
        model="Modelo Z",
        manufacturer="DJI",
        cost_center=centre,
    )
    pilot = Operator.objects.create(
        full_name="Piloto Uno", employee_id="E-9", cost_center=centre
    )
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number="DGAC-0900",
        location="Sector 1",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=5),
        valid_until=TODAY + timedelta(days=30),
    )
    permit.aircraft_fleet.add(aircraft)
    permit.operators.add(pilot)
    permit._aircraft, permit._pilot = aircraft, pilot
    return permit


def _attach(permit, name, content: bytes, two_step=False):
    """Un `Document` de tipo log de vuelo colgado del permiso, con su archivo guardado."""
    key = f"lv427/{name}"
    get_document_storage().save(key, io.BytesIO(content))
    doc = Document(
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        doc_type=DocumentType.objects.get(code="flight-log-txt"),
        title=name,
        file_path="" if two_step else key,
    )
    doc.save()
    if two_step:
        doc.file_path = key
        doc.save(update_fields=["file_path", "updated_at"])
    return doc


def _synthetic(permit, name="vuelo.json"):
    return _attach(permit, name, FIXTURE.read_bytes())


def _analysis_url(analysis):
    return reverse("flight-analysis", args=[analysis.pk])


# ── interfaz de parser ────────────────────────────────────────────────────────


class TestParser:
    def test_the_synthetic_adapter_normalises_and_summarises(self):
        track = parse_flight_log(FIXTURE)

        assert track.synthetic and track.source_format == "synthetic"
        assert len(track.points) == 3
        s = track.summary
        assert s.duration_s == 60
        # Dos tramos de 0,001° de latitud: 2 x 111,19 m.
        assert s.distance_m == pytest.approx(222.4, abs=0.2)
        assert s.max_distance_from_takeoff_m == pytest.approx(222.4, abs=0.2)
        assert s.max_height_m == 50 and s.max_speed_ms == 8
        assert s.takeoff == [10.0, 20.0] and s.landing == [10.002, 20.0]
        assert s.timezone == "UTC-03:00"
        assert [e.level for e in track.events] == ["info", "warning", "critical"]
        assert track.events[1].inferred is True
        assert track.uninterpreted == ["SYNTH_unknown_field_7"]

    def test_the_dji_stub_detects_the_file_and_says_it_is_unavailable(self, tmp_path):
        log = tmp_path / "DJIFlightRecord_2030-01-01.txt"
        log.write_bytes(b"\x00\x01binary")

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(log)
        assert caught.value.code == "parser_unavailable"

    def test_an_unknown_file_is_unsupported(self, tmp_path):
        log = tmp_path / "notes.txt"
        log.write_text("hello")

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(log)
        assert caught.value.code == "unsupported_format"

    def test_a_json_without_the_synthetic_tag_is_not_accepted(self, tmp_path):
        log = tmp_path / "real.json"
        log.write_text(json.dumps({"points": []}))

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(log)
        assert caught.value.code == "unsupported_format"

    def test_a_missing_file_is_incomplete(self, tmp_path):
        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(tmp_path / "gone.json")
        assert caught.value.code == "incomplete"

    def test_without_positions_there_is_not_enough_data(self, tmp_path):
        data = json.loads(FIXTURE.read_text())
        data["points"] = [{"t": 0, "height_m": 1}, {"t": 1, "height_m": 2}]
        log = tmp_path / "nopos.json"
        log.write_text(json.dumps(data))

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(log)
        assert caught.value.code == "insufficient_data"

    def test_points_are_thinned_to_two_thousand(self):
        points = [TrackPoint(t=i, lat=10 + i * 1e-6, lon=20.0) for i in range(5000)]
        thinned = FlightTrack(points=points).downsampled()

        assert len(thinned.points) <= 2000
        assert thinned.points[0].t == 0 and thinned.points[-1].t == 4999
        assert any(x.startswith("points_downsampled:") for x in thinned.limitations)


# ── análisis automático al adjuntar ───────────────────────────────────────────


class TestAttaching:
    def test_attaching_a_log_creates_the_analysis(self, permit):
        doc = _synthetic(permit)

        analysis = FlightLogAnalysis.objects.get(document=doc)
        assert analysis.status == "ok"
        assert analysis.permission == permit
        assert analysis.result["summary"]["max_height_m"] == 50
        assert analysis.analyzed_at is not None

    def test_the_two_step_upload_is_analysed_once_the_file_is_there(self, permit):
        doc = _attach(permit, "vuelo.json", FIXTURE.read_bytes(), two_step=True)

        assert FlightLogAnalysis.objects.filter(document=doc, status="ok").count() == 1

    def test_a_parser_failure_never_breaks_the_upload(self, permit):
        doc = _attach(permit, "DJIFlightRecord_x.txt", b"binary")

        assert Document.objects.filter(pk=doc.pk).exists()
        analysis = FlightLogAnalysis.objects.get(document=doc)
        assert (analysis.status, analysis.error_code) == ("error", "parser_unavailable")

    def test_an_unexpected_crash_in_the_analysis_does_not_break_the_upload(
        self, permit, monkeypatch
    ):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("apps.operations.flightlog.service.analyze_document", boom)
        doc = _synthetic(permit)

        assert Document.objects.filter(pk=doc.pk).exists()
        assert not FlightLogAnalysis.objects.exists()

    def test_other_document_types_are_not_analysed(self, permit):
        other = DocumentType.objects.exclude(code="flight-log-txt").first()
        if other is None:
            other = DocumentType.objects.create(code="otro", name="Otro")
        Document.objects.create(
            content_type=ContentType.objects.get_for_model(FlightPermission),
            object_id=permit.pk,
            doc_type=other,
            title="x.json",
            file_path="lv427/x.json",
        )

        assert not FlightLogAnalysis.objects.exists()

    def test_status_is_constrained(self, permit):
        doc = _synthetic(permit)
        with pytest.raises(IntegrityError), transaction.atomic():
            FlightLogAnalysis.objects.filter(document=doc).update(status="bogus")

    def test_one_analysis_per_document(self, permit):
        doc = _synthetic(permit)
        with pytest.raises(IntegrityError), transaction.atomic():
            FlightLogAnalysis.objects.create(permission=permit, document=doc)

    def test_a_long_log_is_stored_thinned(self, permit):
        data = json.loads(FIXTURE.read_text())
        data["points"] = [
            {"t": i, "lat": 10 + i * 1e-5, "lon": 20.0, "height_m": i % 90}
            for i in range(3000)
        ]
        doc = _attach(permit, "long.json", json.dumps(data).encode())

        analysis = FlightLogAnalysis.objects.get(document=doc)
        assert len(analysis.result["points"]) <= 2000


class TestCommand:
    def test_it_reprocesses_pending_and_missing_and_retries_errors_on_request(
        self, permit
    ):
        doc = _synthetic(permit)
        FlightLogAnalysis.objects.filter(document=doc).update(
            status="pending", result={}
        )
        err = _attach(permit, "DJIFlightRecord_y.txt", b"b")
        assert FlightLogAnalysis.objects.get(document=err).status == "error"

        call_command("analyze_flight_logs")
        assert FlightLogAnalysis.objects.get(document=doc).status == "ok"

        # Se arregla la causa del error y sólo --retry-errors lo vuelve a intentar.
        FlightLogAnalysis.objects.filter(document=err).update(error_code="incomplete")
        call_command("analyze_flight_logs")
        assert FlightLogAnalysis.objects.get(document=err).error_code == "incomplete"
        call_command("analyze_flight_logs", "--retry-errors")
        assert FlightLogAnalysis.objects.get(document=err).error_code == (
            "parser_unavailable"
        )

    def test_record_option_limits_the_run(self, permit):
        doc = _synthetic(permit)
        record = FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            departure_time=time(9),
            arrival_time=time(10),
            pilot=permit._pilot,
            aircraft=permit._aircraft,
        )
        FlightLogAnalysis.objects.filter(document=doc).update(
            status="pending", result={}, flight_record=record
        )

        call_command("analyze_flight_logs", "--record", str(record.pk))
        assert FlightLogAnalysis.objects.get(document=doc).status == "ok"


# ── la pantalla ───────────────────────────────────────────────────────────────


@pytest.fixture
def analysis(permit):
    return FlightLogAnalysis.objects.get(document=_synthetic(permit))


class TestScreen:
    def test_it_shows_the_map_the_synthetic_notice_and_the_summary(self, analysis):
        response = login_as(*READ).get(_analysis_url(analysis))

        assert response.status_code == 200
        html = response.content.decode()
        assert 'id="fa-map"' in html
        match = re.search(
            r'<script id="fa-map-data" type="application/json">(.*?)</script>',
            html,
            re.S,
        )
        data = json.loads(match.group(1))
        assert len(data["points"]) == 3
        assert data["takeoff"] == [10.0, 20.0]
        assert [e["level"] for e in data["events"]] == ["warning", "critical"]
        assert "Datos sintéticos de ejemplo" in html
        assert "UTC-03:00" in html
        assert "SYNTH signal weak" in html
        assert 'class="fa-chart"' in html and "inferido" in html

    def test_it_says_not_provided_when_the_operation_is_missing(self, analysis):
        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()

        assert "No informado" in html
        assert "DGAC-0900" in html and "Faena X" in html

    def test_it_shows_the_operation_data_once_linked(self, analysis, permit):
        record = FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            departure_time=time(9),
            arrival_time=time(10),
            pilot=permit._pilot,
            aircraft=permit._aircraft,
        )
        analysis.flight_record = record
        analysis.save()

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        assert "RPA-9001 · Modelo Z" in html and "Piloto Uno" in html

    def test_it_needs_view_flightrecord(self, analysis):
        assert (
            login_as("view_flightpermission").get(_analysis_url(analysis)).status_code
            == 403
        )
        assert login_as().get(_analysis_url(analysis)).status_code == 403

    def test_another_tenant_cannot_open_it(self, analysis):
        from apps.core.models import OperationalTenant

        other = OperationalTenant.objects.create(name="Otra", slug="otra-427")
        client = login_as(*READ, member_of=other)

        assert client.get(_analysis_url(analysis)).status_code == 404

    def test_an_error_is_shown_in_plain_words(self, permit):
        doc = _attach(permit, "DJIFlightRecord_z.txt", b"b")
        analysis = FlightLogAnalysis.objects.get(document=doc)

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        assert 'data-error-code="parser_unavailable"' in html
        assert "lector de logs de DJI aún no está instalado" in html
        assert 'id="fa-map"' not in html

    def test_linking_an_operation_needs_change_permission(self, analysis, permit):
        record = FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            departure_time=time(9),
            arrival_time=time(10),
            pilot=permit._pilot,
            aircraft=permit._aircraft,
        )
        url = _analysis_url(analysis)

        assert (
            login_as(*READ).post(url, {"flight_record": str(record.pk)}).status_code
            == 403
        )
        client = login_as(*READ, "change_flightrecord")
        assert client.post(url, {"flight_record": str(record.pk)}).status_code == 302
        analysis.refresh_from_db()
        assert analysis.flight_record == record

    def test_the_operations_table_links_to_the_analysis(self, analysis, permit):
        html = (
            login_as(*READ)
            .get(reverse("permission-operations", args=[permit.pk]))
            .content.decode()
        )
        assert _analysis_url(analysis) in html


# ── el CSS propio, con su techo ───────────────────────────────────────────────


def test_the_css_has_its_own_ceiling_and_the_big_sheets_were_not_touched():
    css = ROOT / "static" / "css" / "flight-analysis.css"
    assert css.stat().st_size <= 8 * 1024
    assert "fa-map" not in (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    assert "fa-map" not in (ROOT / "static/css/identity.css").read_text(
        encoding="utf-8"
    )
