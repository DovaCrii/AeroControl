"""LV-434: lo que mostró el primer log real en producción.

1. El log DJI guarda la serie en un campo de 16 caracteres: una serie de 20 llega cortada y el
   análisis avisaba «la serie no coincide» con la aeronave correcta.
2. La cronología repetía cada cambio de modo (el *tip* «Flight mode changed to X.» además del
   evento de `flycState`) y el aviso del gimbal en dos idiomas, con filas «sin explicación».
3. Los análisis ya guardados se rehacen con `analyze_flight_logs --outdated`.

Series y textos inventados con la forma de los reales.
"""

# ruff: noqa: F811 - fixtures compartidas
import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.flightlog import parse_flight_log
from apps.operations.flightlog.independent import same_serial
from apps.operations.flightlog.service import PARSER_VERSION
from apps.operations.flightlog.types import FlightTrack
from apps.operations.flightlog.views import registry_aircraft
from apps.operations.models import FlightLogAnalysis
from apps.registry.models import Aircraft

from .test_lv427_flight_log_analysis import centre, isolated_storage  # noqa: F401
from .test_lv429_dji_adapter import _log, dji_output, fake  # noqa: F401
from .test_lv431_flight_logs_section import ADD, VIEW, _upload, drone  # noqa: F401

FULL = "9999X9XXX999999X999X"  # 20 caracteres, como la de un Mavic 3E
CUT = FULL[:16]


class TestSerial:
    def test_the_16_character_cut_matches_the_registered_serial(self):
        assert same_serial(CUT, FULL)
        assert same_serial(FULL, FULL)

    def test_any_other_partial_serial_does_not(self):
        assert not same_serial(FULL[:15], FULL)  # no es el corte del formato
        assert not same_serial(CUT, "0" + FULL)  # no empieza igual
        assert not same_serial(None, FULL) and not same_serial(CUT, "")

    def test_the_registry_finds_the_aircraft_from_the_cut_serial(self, drone):
        drone.serial_number = FULL
        drone.save()
        track = FlightTrack(aircraft={"serial": CUT})

        assert registry_aircraft(track, drone.tenant_id) == drone

    def test_two_aircraft_sharing_the_cut_match_none(self, drone):
        drone.serial_number = FULL
        drone.save()
        twin = Aircraft.objects.get(pk=drone.pk)
        twin.pk = None
        twin.registration = "RPA-TWIN"
        twin.serial_number = CUT + "0000"
        twin.save()
        track = FlightTrack(aircraft={"serial": CUT})

        assert registry_aircraft(track, drone.tenant_id) is None

    def test_no_mismatch_warning_for_the_cut_serial(self, fake, drone, centre):
        drone.serial_number = FULL
        drone.save()
        fake.output["details"]["aircraftSn"] = CUT
        client = login_as(VIEW, ADD)
        _upload(client, centre, drone)
        analysis = FlightLogAnalysis.objects.get()

        page = client.get(reverse("flight-analysis", args=[analysis.pk]))
        assert page.context["serial_warning"] == ""


def _rows(*tips):
    """Cuadros sintéticos con los *tips* dados en el cuadro t=120."""
    rows = [
        (0, 10.0, 20.0, "EngineStart", "", "", 90),
        (60, 10.001, 20.0, "GPSWaypoint", "", "", 60),
    ]
    rows.append((120, 10.002, 20.0, "GoHome", "; ".join(tips), "", 30))
    rows.append((130, 10.0, 20.0, "AutoLanding", "", "", 25))
    return rows


class TestTimeline:
    def test_the_mode_change_tip_is_not_a_second_row(self, fake, tmp_path):
        fake.output = dji_output(_rows("Flight mode changed to GoHome."))
        events = parse_flight_log(_log(tmp_path)).events

        assert not [e for e in events if e.raw_text.startswith("Flight mode")]
        assert [e.code for e in events if e.t == 120] == ["mode:GoHome"]

    def test_the_gimbal_notice_in_two_languages_is_one_row(self, fake, tmp_path):
        fake.output = dji_output(
            _rows(
                "Gimbal yaw axis endpoint reached.",
                "Se ha alcanzado el límite del eje de paneo del estabilizador 1",
            )
        )
        events = parse_flight_log(_log(tmp_path)).events
        gimbal = [e for e in events if e.code == "tip:gimbal_limit"]

        assert len(gimbal) == 1

    def test_different_notices_in_the_same_frame_stay(self, fake, tmp_path):
        fake.output = dji_output(_rows("Gimbal limit reached", "Some unrecognised tip"))
        texts = {e.raw_text for e in parse_flight_log(_log(tmp_path)).events}

        assert {"Gimbal limit reached", "Some unrecognised tip"} <= texts


class TestOutdated:
    def test_outdated_analyses_are_redone_and_current_ones_are_not(
        self, fake, drone, centre
    ):
        client = login_as(VIEW, ADD)
        _upload(client, centre, drone)
        analysis = FlightLogAnalysis.objects.get()
        FlightLogAnalysis.objects.filter(pk=analysis.pk).update(parser_version="dji-1")
        calls = len(fake.calls)

        call_command("analyze_flight_logs", "--outdated")
        analysis.refresh_from_db()
        assert analysis.parser_version == PARSER_VERSION
        assert len(fake.calls) == calls + 1

        call_command("analyze_flight_logs", "--outdated")
        assert len(fake.calls) == calls + 1  # ya al día: no se rehace

    def test_without_the_flag_finished_analyses_are_left_alone(
        self, fake, drone, centre
    ):
        client = login_as(VIEW, ADD)
        _upload(client, centre, drone)
        FlightLogAnalysis.objects.update(parser_version="dji-1")
        calls = len(fake.calls)

        call_command("analyze_flight_logs")
        assert len(fake.calls) == calls
        assert FlightLogAnalysis.objects.get().parser_version == "dji-1"


@pytest.fixture(autouse=True)
def _db(db):
    return db
