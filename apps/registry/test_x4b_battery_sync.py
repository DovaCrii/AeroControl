"""X.4b: mirroring AeroLink's battery inventory (ADR-0002 phase 2).

`Battery` was created empty on purpose (R7.2) because ADR-0002 makes AeroLink
the master. These cover the consumer side end to end **before AeroLink exposes
anything**, through `--from-file`, so the contract can be agreed against
something that runs rather than against a description.
"""

import json

import pytest
from django.core.management import CommandError, call_command

from apps.registry.aerolink import AeroLinkUnavailable, parse_batteries
from apps.registry.models import Aircraft, Battery


def _payload(*batteries):
    return {"results": list(batteries)}


def _battery(serial="BAT-001", **overrides):
    entry = {
        "serial_number": serial,
        "model": "TB65",
        "status": "active",
        "cycle_count": 120,
        "health_percent": 93,
        "firmware_version": "03.00.05",
    }
    entry.update(overrides)
    return entry


def _write(tmp_path, payload):
    path = tmp_path / "batteries.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class TestTheContractParsing:
    def test_accepts_the_results_envelope(self):
        assert len(parse_batteries(json.dumps(_payload(_battery())).encode())) == 1

    def test_accepts_a_bare_list(self):
        """AeroLink's API is not written yet; refusing the simpler shape would
        impose a requirement on their side for no benefit here."""
        assert len(parse_batteries(json.dumps([_battery()]).encode())) == 1

    def test_malformed_json_is_reported_not_swallowed(self):
        with pytest.raises(AeroLinkUnavailable):
            parse_batteries(b"{not json")

    def test_an_unexpected_shape_is_reported(self):
        with pytest.raises(AeroLinkUnavailable):
            parse_batteries(json.dumps({"results": "nope"}).encode())


class TestTheSync:
    @pytest.mark.django_db
    def test_creates_a_battery_from_the_feed(self, tmp_path):
        call_command(
            "sync_batteries", "--from-file", _write(tmp_path, _payload(_battery()))
        )

        battery = Battery.objects.get()
        assert battery.serial_number == "BAT-001"
        assert battery.cycle_count == 120
        assert battery.health_percent == 93
        assert battery.firmware_version == "03.00.05"
        # Where it came from and how fresh it is -- without these a zero cycle
        # count is ambiguous (new battery, or a sync that never ran?).
        assert battery.source == Battery.SOURCE_AEROLINK
        assert battery.synced_at is not None

    @pytest.mark.django_db
    def test_running_twice_updates_instead_of_duplicating(self, tmp_path):
        first = _write(tmp_path, _payload(_battery()))
        call_command("sync_batteries", "--from-file", first)
        second = _write(tmp_path, _payload(_battery(cycle_count=145)))
        call_command("sync_batteries", "--from-file", second)

        assert Battery.objects.count() == 1
        assert Battery.objects.get().cycle_count == 145

    @pytest.mark.django_db
    def test_the_serial_is_normalized_like_everywhere_else(self, tmp_path):
        """A serial typed by a human and one arriving from telemetry must
        compare equal (X.1)."""
        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery(serial="BAT 001 "))),
        )

        assert Battery.objects.get().serial_number == "BAT001"

    @pytest.mark.django_db
    def test_an_omitted_field_does_not_overwrite_what_is_known(self, tmp_path):
        """ "AeroLink did not say" is not "AeroLink said zero". Overwriting a
        known cycle count with 0 because a key was missing would destroy the
        evidence this table exists for."""
        call_command(
            "sync_batteries", "--from-file", _write(tmp_path, _payload(_battery()))
        )
        stripped = {"serial_number": "BAT-001"}
        call_command(
            "sync_batteries", "--from-file", _write(tmp_path, _payload(stripped))
        )

        battery = Battery.objects.get()
        assert battery.cycle_count == 120
        assert battery.health_percent == 93

    @pytest.mark.django_db
    def test_links_to_the_aircraft_by_serial(self, tmp_path):
        aircraft = Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="AIR-9",
        )

        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery(aircraft_serial="AIR-9"))),
        )

        assert Battery.objects.get().aircraft == aircraft

    @pytest.mark.django_db
    def test_an_unknown_aircraft_serial_is_ignored_not_fatal(self, tmp_path):
        """Batteries rotate between airframes and AeroLink may know an aircraft
        this padrón does not. That is not a reason to drop the battery."""
        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery(aircraft_serial="NOT-HERE"))),
        )

        assert Battery.objects.get().aircraft is None

    @pytest.mark.django_db
    def test_an_entry_with_no_serial_is_skipped(self, tmp_path):
        """It cannot be matched to anything, now or later; inventing a key
        would be worse."""
        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload({"model": "TB65"}, _battery())),
        )

        assert Battery.objects.count() == 1

    @pytest.mark.django_db
    def test_a_battery_missing_from_the_feed_is_never_deleted(self, tmp_path):
        """A partial answer is likelier than a battery that ceased to exist,
        and deleting it would take its cycle history with it."""
        call_command(
            "sync_batteries", "--from-file", _write(tmp_path, _payload(_battery()))
        )

        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery(serial="BAT-002"))),
        )

        assert Battery.objects.count() == 2
        assert Battery.objects.filter(serial_number="BAT-001").exists()

    @pytest.mark.django_db
    def test_dry_run_writes_nothing(self, tmp_path):
        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery())),
            "--dry-run",
        )

        assert Battery.objects.count() == 0

    @pytest.mark.django_db
    def test_an_out_of_range_health_is_ignored(self, tmp_path):
        """The model has a CheckConstraint for this; the sync must not be the
        thing that trips it."""
        call_command(
            "sync_batteries",
            "--from-file",
            _write(tmp_path, _payload(_battery(health_percent=140))),
        )

        assert Battery.objects.get().health_percent is None

    @pytest.mark.django_db
    def test_a_missing_file_fails_clearly(self):
        with pytest.raises(CommandError):
            call_command("sync_batteries", "--from-file", "nope.json")


class TestTheGatewayIsOptIn:
    @pytest.mark.django_db
    def test_with_no_url_configured_the_command_fails_loudly(self, settings):
        """Not "0 batteries": an empty inventory and an unreachable gateway
        must not look the same in the job log."""
        settings.AEROLINK_API_URL = ""

        with pytest.raises(CommandError):
            call_command("sync_batteries")

    @pytest.mark.django_db
    def test_a_non_http_url_is_refused(self, settings):
        """urlopen would accept file://, turning a misconfigured setting into a
        local-file read."""
        settings.AEROLINK_API_URL = "file:///etc/passwd"

        with pytest.raises(CommandError):
            call_command("sync_batteries")
