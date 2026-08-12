"""X.4c: serials are upper-cased, as ADR-0002 §2 always said they should be.

The ADR settled on "mayúsculas, sin espacios" from the start; AeroControl had
only ever implemented the whitespace half. That was harmless while AeroControl
talked to itself, and becomes a silent failure the moment AeroLink normalizes
as written: an exact-match lookup stops matching, so a battery never finds its
airframe and a hand-entered one gets duplicated instead of updated.
"""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.registry.models import Aircraft, Battery, normalize_serial


class TestNormalizeSerial:
    def test_upper_cases(self):
        assert normalize_serial("1581f5fhc245700d181d") == "1581F5FHC245700D181D"

    def test_strips_whitespace_inside_not_just_at_the_ends(self):
        """Two real aircraft carry a spurious space mid-serial (RPA-4401,
        RPA-4436)."""
        assert normalize_serial(" 1581 f5fh c245 ") == "1581F5FHC245"

    def test_empty_becomes_none(self):
        """Aircraft.serial_number is nullable and unique: empty strings would
        collide with each other on the index."""
        assert normalize_serial("") is None
        assert normalize_serial("   ") is None
        assert normalize_serial(None) is None

    def test_lengths_are_not_padded_or_truncated(self):
        """14- and 20-character serials coexist (Matrice 300 vs Mavic 3)."""
        assert normalize_serial("1581F5FHC245700D181D") == "1581F5FHC245700D181D"
        assert normalize_serial("12345678901234") == "12345678901234"


class TestTheModelsUseIt:
    @pytest.mark.django_db
    def test_aircraft_stores_upper_case(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number=" 1581f5 fhc245 ",
        )

        aircraft.refresh_from_db()
        assert aircraft.serial_number == "1581F5FHC245"

    @pytest.mark.django_db
    def test_battery_stores_upper_case(self, db):
        battery = Battery.objects.create(serial_number="tb65-abc")

        battery.refresh_from_db()
        assert battery.serial_number == "TB65-ABC"

    @pytest.mark.django_db
    def test_a_lower_case_serial_no_longer_hides_from_an_upper_case_lookup(self, db):
        """The whole point: this exact-match lookup is how sync_batteries
        resolves an aircraft, and how the padrón API answers AeroLink."""
        Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="abc123",
        )

        assert Aircraft.objects.filter(serial_number="ABC123").exists()


class TestThePadronApiNormalizesTheQuery:
    @pytest.mark.django_db
    def test_a_lower_case_query_finds_the_aircraft(self, db):
        from django.contrib.auth.models import Permission, User
        from rest_framework.test import APIClient

        Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="ABC123",
        )
        user = User.objects.create_user("gateway", password="pw")
        user.user_permissions.add(Permission.objects.get(codename="view_aircraft"))
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            reverse("api-v1-registry-aircraft"), {"serial": "abc 123"}
        )

        assert response.status_code == 200
        assert response.data["count"] == 1


class TestTheAuditCommand:
    @pytest.mark.django_db
    def test_reports_nothing_when_everything_is_upper_case(self, db, capsys):
        Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="ABC123",
        )

        call_command("audit_serial_case")

        assert "already upper-case" in capsys.readouterr().out

    @pytest.mark.django_db
    def test_reports_a_row_that_needs_normalizing(self, db, capsys):
        """Written straight to the column, bypassing save(), which is exactly
        the state a pre-X.4c database is in."""
        aircraft = Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="ABC123",
        )
        Aircraft.objects.filter(pk=aircraft.pk).update(serial_number="abc123")

        call_command("audit_serial_case")

        output = capsys.readouterr().out
        assert "'abc123'" in output
        assert "need attention" in output

    @pytest.mark.django_db
    def test_reports_a_collision_that_a_migration_could_not_resolve(self, db, capsys):
        """Two serials differing only in case cannot both be upper-cased: the
        column is unique. Which one is right comes from the DGAC certificate,
        not from a guess."""
        first = Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="ABC123",
        )
        second = Aircraft.objects.create(
            registration="CC-A2",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            serial_number="PLACEHOLDER",
        )
        Aircraft.objects.filter(pk=second.pk).update(serial_number="abc123")
        assert first.pk != second.pk

        call_command("audit_serial_case")

        assert "COLLISION" in capsys.readouterr().out
