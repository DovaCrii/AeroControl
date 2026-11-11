"""LV-429 (fase 2): lector de logs DJI real.

El binario `dji-log-json` no se ejecuta nunca acá: `subprocess.run` se simula con un monkeypatch y
la salida es un fixture sintético con la forma exacta del envoltorio (coordenadas y serie
inventadas). La clave de DJI de prueba es ficticia.
"""

# ruff: noqa: F811 - las fixtures `permit` y `centre` se importan de la prueba de LV-427
import copy
import io
import json
import logging
import re
import subprocess
from types import SimpleNamespace

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import translation

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.flightlog import FlightLogError, parse_flight_log
from apps.operations.flightlog import dji as dji_module
from apps.operations.flightlog.narrative import build_narrative
from apps.operations.flightlog.service import analyze_document
from apps.operations.flightlog.types import FlightTrack
from apps.operations.flightlog.views import map_payload
from apps.operations.models import FlightLogAnalysis, FlightPermission
from apps.registry.models import Aircraft, CostCenter

from .test_lv427_flight_log_analysis import (  # noqa: F401 - fixtures compartidas
    READ,
    _analysis_url,
    centre,
    isolated_storage,
    permit,
)

KEY = "sk-test-key-0123456789"
SERIAL = "SYNTH-SN-001"
TIP_RTH = (
    "La batería restante solo es suficiente para RPO. Regresa al punto de origen ahora."
)
TIP_GIMBAL = "Gimbal limit reached"
TIP_OTHER = "Some unrecognised tip"
WARN_HOME = "Flight mode changed to GoHome."

# (t, lat, lon, modo, tip, warn, batería)
_ROWS = [
    (0, 10.0, 20.0, "EngineStart", "", "", 90),
    (1, 10.0, 20.0, "AutoTakeoff", "", "", 90),
    (60, 10.001, 20.0, "GPSWaypoint", "", "", 60),
    (120, 10.002, 20.0, "GPSWaypoint", f"{TIP_RTH}; {TIP_GIMBAL}", "", 30),
    (121, 10.002, 20.0, "GPSWaypoint", f"{TIP_RTH}; {TIP_GIMBAL}", "", 30),
    (122, 10.002, 20.0, "GPSWaypoint", f"{TIP_GIMBAL}; {TIP_OTHER}", "", 29),
    (123, 10.002, 20.0, "GPSWaypoint", TIP_RTH, "", 29),
    (180, 10.001, 20.0, "GoHome", "", WARN_HOME, 20),
    (240, 10.0001, 20.0, "AutoLanding", "", "", 15),
    (250, 10.00005, 20.0, "ConfirmLanding", "", "", 13),
]


def dji_output(rows=None, **details):
    """Lo que imprime `dji-log-json`: `{"version", "details", "frames"}` (camelCase)."""
    frames = []
    for t, lat, lon, mode, tip, warn, battery in rows or _ROWS:
        frames.append(
            {
                "osd": {
                    "latitude": lat,
                    "longitude": lon,
                    "height": min(t, 101) * 1.0,
                    "altitude": 500.0,
                    "flyTime": float(t),
                    "xSpeed": 3.0,
                    "ySpeed": 4.0,
                    "zSpeed": 0.0,
                    "gpsNum": 17,
                    "flycState": mode,
                    "goHomeStatus": "Standby",
                    "isOnGround": False,
                },
                "battery": {"chargeLevel": battery, "voltage": 15.2},
                "home": {"latitude": 10.0, "longitude": 20.0},
                "app": {"tip": tip, "warn": warn},
                "rc": {"uplinkSignal": 4, "downlinkSignal": 4},
                "custom": {"dateTime": "2030-01-15T13:00:00Z"},
            }
        )
    base = {
        "aircraftName": "Synthetic aircraft",
        "aircraftSn": SERIAL,
        "appPlatform": "Android",
        "appVersion": "1.0.0",
        "productType": "Mavic3Enterprise",
        "startTime": "2030-01-15T13:00:00Z",
        "totalTime": 250.0,
        "totalDistance": 0.5,  # km
        "maxHeight": 101.0,
        "maxHorizontalSpeed": 5.0,
        "takeOffAltitude": 100.0,
        "latitude": 10.0,
        "longitude": 20.0,
        "city": "Map Loading",
        "area": "",
    }
    base.update(details)
    return {"version": 14, "details": base, "frames": frames}


class FakeRun:
    """Sustituye `subprocess.run`: registra cada llamada y se comporta como el envoltorio
    (crea el archivo de llaves la primera vez y lo reutiliza la segunda)."""

    def __init__(self):
        self.output = dji_output()
        self.returncode = 0
        self.stderr = b""
        self.raises = None
        self.calls = []
        self.cache_seen = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if self.raises:
            raise self.raises
        if "--keychains" in command:
            cache = command[command.index("--keychains") + 1]
            try:
                with open(cache, "rb") as handle:
                    self.cache_seen.append(handle.read())
            except FileNotFoundError:
                self.cache_seen.append(None)
                with open(cache, "wb") as handle:
                    handle.write(b'{"keychains": 1}')
        stdout = json.dumps(self.output).encode() if self.returncode == 0 else b""
        return SimpleNamespace(
            returncode=self.returncode, stdout=stdout, stderr=self.stderr
        )


@pytest.fixture
def fake(monkeypatch, settings):
    settings.DJI_LOG_PARSER_BIN = "/opt/fake/dji-log-json"
    settings.DJI_API_KEY = KEY
    runner = FakeRun()
    monkeypatch.setattr(dji_module.subprocess, "run", runner)
    return runner


def _log(tmp_path):
    path = tmp_path / "DJIFlightRecord_2030-01-15.txt"
    path.write_bytes(b"\x00binary")
    return path


def _attach_dji(permit, name="DJIFlightRecord_2030-01-15.txt"):
    key = f"lv429/{name}"
    get_document_storage().save(key, io.BytesIO(b"\x00binary"))
    return Document.objects.create(
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        doc_type=DocumentType.objects.get(code="flight-log-txt"),
        title=name,
        file_path=key,
    )


def _stderr(code, message="boom"):
    return json.dumps({"error": code, "message": message}).encode()


# ── mapeo de puntos y resumen ─────────────────────────────────────────────────


class TestMapping:
    def test_points_and_summary(self, fake, tmp_path):
        track = parse_flight_log(_log(tmp_path))

        assert track.source_format == "dji" and not track.synthetic
        assert len(track.points) == len(_ROWS)
        mid = track.points[2]
        assert mid.t == 60 and mid.lat == 10.001 and mid.lon == 20.0
        assert mid.height_m == 60 and mid.battery_pct == 60 and mid.satellites == 17
        assert mid.speed_ms == pytest.approx(5.0)  # hipot(3, 4)
        s = track.summary
        assert s.distance_m == 500.0  # `totalDistance` viene en km
        assert s.duration_s == 250.0
        assert s.max_height_m == 101 and s.max_speed_ms == pytest.approx(5.0)
        assert s.takeoff == [10.0, 20.0] and s.landing == [10.00005, 20.0]

    def test_start_time_is_local_and_utc(self, fake, tmp_path):
        s = parse_flight_log(_log(tmp_path)).summary

        assert s.timezone == "America/Santiago"
        assert s.started_at == "2030-01-15T10:00:00-03:00"  # verano austral: UTC-3
        assert s.started_at_utc == "2030-01-15T13:00:00+00:00"

    def test_aircraft_is_what_the_log_says_and_nothing_more(self, fake, tmp_path):
        track = parse_flight_log(_log(tmp_path))

        assert track.aircraft == {"log_model": "Mavic 3 Enterprise", "serial": SERIAL}

    def test_a_frame_without_position_is_kept_without_coordinates(self, fake, tmp_path):
        fake.output["frames"][2]["osd"]["latitude"] = 0.0
        fake.output["frames"][2]["osd"]["longitude"] = 0.0

        track = parse_flight_log(_log(tmp_path))
        assert (track.points[2].lat, track.points[2].lon) == (None, None)

    def test_without_positions_there_is_not_enough_data(self, fake, tmp_path):
        for frame in fake.output["frames"]:
            frame["osd"]["latitude"] = None

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "insufficient_data"


# ── eventos ───────────────────────────────────────────────────────────────────


class TestEvents:
    def test_texts_are_split_and_not_repeated_in_consecutive_frames(
        self, fake, tmp_path
    ):
        track = parse_flight_log(_log(tmp_path))
        texts = [
            (e.t, e.raw_text)
            for e in track.events
            if e.code.startswith(("tip", "warn"))
        ]

        assert texts == [
            (120, TIP_GIMBAL),
            (120, TIP_RTH),
            (122, TIP_OTHER),
            (123, TIP_RTH),  # reaparece tras ausentarse: aparición nueva
            (180, WARN_HOME),
        ]

    def test_levels_codes_and_unrecognised_text(self, fake, tmp_path):
        events = {e.raw_text: e for e in parse_flight_log(_log(tmp_path)).events}

        assert (
            events[TIP_RTH].level == "info"
            and events[TIP_RTH].code == "tip:low_battery_rth"
        )
        assert events[TIP_GIMBAL].code == "tip:gimbal_limit"
        assert events[WARN_HOME].level == "warning" and events[WARN_HOME].code == "warn"
        other = events[TIP_OTHER]
        assert (other.code, other.explanation, other.inferred) == ("tip", "", False)

    def test_mode_changes_and_the_return_leg(self, fake, tmp_path):
        track = parse_flight_log(_log(tmp_path))
        modes = [(e.t, e.code) for e in track.events if e.code.startswith("mode:")]

        assert modes == [
            (0, "mode:EngineStart"),
            (1, "mode:AutoTakeoff"),
            (60, "mode:GPSWaypoint"),
            (180, "mode:GoHome"),
            (240, "mode:AutoLanding"),
            (250, "mode:ConfirmLanding"),
        ]
        assert track.return_leg == [180, 250]

    def test_a_status_based_return_starts_the_leg_too(self, fake, tmp_path):
        for frame in fake.output["frames"][5:]:
            frame["osd"]["flycState"] = "GPSWaypoint"
        fake.output["frames"][6]["osd"]["goHomeStatus"] = "Navigating"

        track = parse_flight_log(_log(tmp_path))
        assert track.return_leg == [123, 250]
        assert any(e.code == "auto_return_status" for e in track.events)

    def test_no_return_means_no_leg(self, fake, tmp_path):
        fake.output["frames"][7]["osd"]["flycState"] = "GPSWaypoint"

        assert parse_flight_log(_log(tmp_path)).return_leg is None

    def test_known_events_are_explained_and_the_original_text_stays(self, fake, permit):
        doc = _attach_dji(permit)
        analysis = FlightLogAnalysis.objects.get(document=doc)

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        assert "sólo alcanza para volver al punto de origen" in html
        assert TIP_RTH in html and WARN_HOME in html
        assert "despegó de forma automática" in html
        # lo no reconocido: sin explicación inventada
        assert (
            TIP_OTHER in html and "no tiene una explicación en lenguaje claro" in html
        )


# ── mapa ──────────────────────────────────────────────────────────────────────


class TestMap:
    def test_one_marker_when_takeoff_and_landing_coincide(self, fake, tmp_path):
        track = parse_flight_log(_log(tmp_path))
        payload = map_payload(track)

        assert payload["sameSpot"] is True  # ~5,5 m
        assert payload["i18n"]["takeoffLanding"]

    def test_two_markers_when_they_are_apart(self, fake, tmp_path):
        fake.output["frames"][-1]["osd"]["latitude"] = 10.001  # ~111 m
        payload = map_payload(parse_flight_log(_log(tmp_path)))

        assert payload["sameSpot"] is False

    def test_the_return_path_is_the_leg_only(self, fake, tmp_path):
        payload = map_payload(parse_flight_log(_log(tmp_path)))

        assert payload["returnPath"] == [
            [10.001, 20.0],
            [10.0001, 20.0],
            [10.00005, 20.0],
        ]

    def test_the_page_carries_the_map_data_and_mentions_the_return(self, fake, permit):
        doc = _attach_dji(permit)
        analysis = FlightLogAnalysis.objects.get(document=doc)

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        data = json.loads(
            re.search(
                r'<script id="fa-map-data" type="application/json">(.*?)</script>',
                html,
                re.S,
            ).group(1)
        )
        assert data["sameSpot"] is True and len(data["returnPath"]) == 3
        assert [t["id"] for t in data["tiles"]] == ["streets", "satellite"]
        assert "línea discontinua" in html

    def test_the_script_offers_every_layer_and_draws_the_return(self):
        from pathlib import Path

        js = (
            Path(__file__).resolve().parents[2] / "static/js/flight-analysis.js"
        ).read_text(encoding="utf-8")
        assert "L.control.layers" in js and 'dashArray: "8 8"' in js
        assert "data.sameSpot" in js and "data.i18n.takeoffLanding" in js


# ── resumen escrito ───────────────────────────────────────────────────────────


class TestNarrative:
    def test_it_states_only_facts_from_the_log(self, fake, tmp_path):
        track = parse_flight_log(_log(tmp_path))

        with translation.override("en"):
            result = build_narrative(track)
        assert result["text"] == (
            "The flight lasted 4 min, covered 0.5 km and reached 101 m above the takeoff "
            "point. At minute 2 the aircraft warned that the battery was only enough to "
            "return, and it flew back in automatic mode. It landed with 13% battery."
        )
        assert result["low_battery"] == "Low battery at landing: 13%, under 20%."

    def test_a_healthy_battery_is_not_flagged(self, fake, tmp_path):
        fake.output["frames"][-1]["battery"]["chargeLevel"] = 45
        track = parse_flight_log(_log(tmp_path))

        assert build_narrative(track)["low_battery"] == ""

    def test_without_a_warning_it_does_not_claim_one(self, fake, tmp_path):
        rows = [r for r in _ROWS if r[4] == "" and r[5] == ""]
        fake.output = dji_output([r for r in rows if r[3] != "GoHome"])
        track = parse_flight_log(_log(tmp_path))

        with translation.override("en"):
            text = build_narrative(track)["text"]
        assert "warned" not in text and "automatic return" not in text

    def test_the_low_battery_notice_reaches_the_page(self, fake, permit):
        doc = _attach_dji(permit)
        analysis = FlightLogAnalysis.objects.get(document=doc)

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        assert 'id="fa-narrative"' in html and 'id="fa-low-battery"' in html


# ── aeronave: cruce con el registro por número de serie ──────────────────────


class TestRegistryMatch:
    def _page(self, permit):
        doc = _attach_dji(permit)
        analysis = FlightLogAnalysis.objects.get(document=doc)
        return login_as(*READ).get(_analysis_url(analysis)).content.decode()

    def test_same_tenant_aircraft_is_shown_from_the_registry(self, fake, permit):
        aircraft = Aircraft.objects.create(
            registration="RPA-9100",
            serial_number=f" {SERIAL.lower()} ",  # se normaliza al guardar
            type="RPA",
            model="Registro M3E",
            manufacturer="DJI",
            cost_center=permit.cost_center,
        )
        assert aircraft.serial_number == SERIAL

        html = self._page(permit)
        assert "RPA-9100 · Registro M3E" in html
        assert "Centro de costo de la aeronave" in html and "Faena X" in html
        assert "según el log" not in html

    def test_another_tenant_aircraft_is_never_matched(self, fake, permit):
        other = OperationalTenant.objects.create(name="Otra", slug="otra-429")
        other_centre = CostCenter.objects.create(
            code="CC901", name="Faena ajena", operates_flights=True, tenant=other
        )
        Aircraft.objects.create(
            registration="RPA-9200",
            serial_number=SERIAL,
            type="RPA",
            model="Ajena",
            manufacturer="DJI",
            cost_center=other_centre,
            tenant=other,
        )

        html = self._page(permit)
        assert "RPA-9200" not in html and "Faena ajena" not in html
        assert "No informado" in html
        assert "Mavic 3 Enterprise (según el log)" in html

    def test_no_serial_in_the_registry_marks_the_model_as_the_logs(self, fake, permit):
        html = self._page(permit)

        assert "No informado · Mavic 3 Enterprise (según el log)" in html


# ── errores del envoltorio ────────────────────────────────────────────────────


class TestErrors:
    @pytest.mark.parametrize(
        ("wrapper_code", "expected"),
        [
            ("missing_api_key", "missing_api_key"),
            ("unsupported_format", "unsupported_format"),
            ("incomplete", "incomplete"),
            ("keychain_error", "keychain_error"),
            ("read_error", "incomplete"),
            ("usage", "incomplete"),
            ("something_new", "incomplete"),
        ],
    )
    def test_each_stderr_code_has_its_flight_log_error(
        self, fake, tmp_path, wrapper_code, expected
    ):
        fake.returncode, fake.stderr = 2, _stderr(wrapper_code, "details")

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == expected
        assert caught.value.code in FlightLogError.CODES

    def test_garbage_on_stderr_is_an_incomplete_log(self, fake, tmp_path):
        fake.returncode, fake.stderr = 1, b"thread panicked"

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "incomplete"

    def test_unreadable_stdout_is_an_incomplete_log(self, fake, tmp_path, monkeypatch):
        monkeypatch.setattr(
            dji_module.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                returncode=0, stdout=b"no json", stderr=b""
            ),
        )
        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "incomplete"

    def test_without_a_configured_binary_the_reader_is_unavailable(
        self, fake, tmp_path, settings
    ):
        settings.DJI_LOG_PARSER_BIN = ""

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "parser_unavailable"
        assert fake.calls == []

    def test_a_binary_that_cannot_start_is_unavailable(self, fake, tmp_path):
        fake.raises = FileNotFoundError("no such file")

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "parser_unavailable"

    def test_a_timeout_is_a_clear_error(self, fake, tmp_path):
        fake.raises = subprocess.TimeoutExpired(cmd="x", timeout=120)

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert caught.value.code == "incomplete" and "too long" in caught.value.message

    def test_the_error_reaches_the_page_in_plain_words(self, fake, permit):
        fake.returncode, fake.stderr = 2, _stderr("keychain_error")
        doc = _attach_dji(permit)
        analysis = FlightLogAnalysis.objects.get(document=doc)

        html = login_as(*READ).get(_analysis_url(analysis)).content.decode()
        assert 'data-error-code="keychain_error"' in html
        assert "DJI no entregó las llaves" in html


# ── la clave ──────────────────────────────────────────────────────────────────


class TestApiKey:
    def test_the_key_goes_only_in_the_child_environment(self, fake, tmp_path):
        parse_flight_log(_log(tmp_path))

        command, kwargs = fake.calls[0]
        assert isinstance(command, list) and not kwargs.get("shell")
        assert all(KEY not in str(part) for part in command)
        assert kwargs["env"]["DJI_API_KEY"] == KEY
        assert kwargs["timeout"] == 120 and kwargs["capture_output"] is True

    def test_the_key_is_not_inherited_from_the_parent_environment(
        self, fake, tmp_path, monkeypatch, settings
    ):
        settings.DJI_API_KEY = ""
        monkeypatch.setenv("SECRET_FROM_PARENT", "x")
        parse_flight_log(_log(tmp_path))

        env = fake.calls[0][1]["env"]
        assert "DJI_API_KEY" not in env and "SECRET_FROM_PARENT" not in env

    def test_the_key_never_appears_in_errors_or_logs(self, fake, tmp_path, caplog):
        fake.returncode = 2
        fake.stderr = _stderr("keychain_error", f"request rejected for key {KEY}")
        caplog.set_level(logging.DEBUG)

        with pytest.raises(FlightLogError) as caught:
            parse_flight_log(_log(tmp_path))
        assert KEY not in caught.value.message and KEY not in str(caught.value)
        assert KEY not in caplog.text

    def test_the_key_stays_out_of_the_stored_analysis(self, fake, permit, caplog):
        fake.returncode = 2
        fake.stderr = _stderr("keychain_error", f"rejected {KEY}")
        caplog.set_level(logging.DEBUG)

        analysis = FlightLogAnalysis.objects.get(document=_attach_dji(permit))
        assert KEY not in analysis.error_message and KEY not in caplog.text


# ── caché de llaves por documento ─────────────────────────────────────────────


class TestKeychainCache:
    def test_the_second_reading_reuses_the_stored_keys(self, fake, permit):
        doc = _attach_dji(permit)
        key = f"flightlog-keychains/{doc.pk}.json"

        # 1.ª lectura (al adjuntar): no había llaves; el lector las dejó y se guardaron.
        assert fake.cache_seen == [None]
        assert get_document_storage().exists(key)
        assert get_document_storage().open(key).read() == b'{"keychains": 1}'

        # 2.ª lectura: se le entrega el archivo de llaves ya guardado (sin red en el CLI real).
        analyze_document(doc)
        assert fake.cache_seen[1] == b'{"keychains": 1}'
        first, second = fake.calls[0][0], fake.calls[1][0]
        assert "--keychains" in first and "--keychains" in second

    def test_the_cache_lives_in_private_storage_not_in_the_repo(
        self, fake, permit, settings
    ):
        doc = _attach_dji(permit)

        stored = settings.DOCUMENTS_ROOT / "flightlog-keychains" / f"{doc.pk}.json"
        assert stored.is_file()

    def test_a_failure_without_keys_stores_no_cache(self, fake, permit):
        fake.returncode, fake.stderr = 2, _stderr("missing_api_key")
        fake.output = copy.deepcopy(fake.output)
        doc = _attach_dji(permit)

        assert not get_document_storage().exists(f"flightlog-keychains/{doc.pk}.json")
        analysis = FlightLogAnalysis.objects.get(document=doc)
        assert analysis.error_code == "missing_api_key"


def test_the_stored_result_round_trips(fake, tmp_path):
    track = parse_flight_log(_log(tmp_path))
    again = FlightTrack.from_dict(json.loads(json.dumps(track.to_dict())))

    assert again.aircraft == track.aircraft and again.return_leg == [180, 250]
    assert again.summary.started_at_utc == track.summary.started_at_utc
