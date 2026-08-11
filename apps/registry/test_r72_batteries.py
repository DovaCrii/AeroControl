"""R7.2 (ISO 7.1.3): LiPo inventory and cycle count, as a mirror of AeroLink.

What matters here is not CRUD (there is none, by design) but the properties
that make the table trustworthy as ISO evidence: the serial joins to what DJI
reports, provenance is recorded rather than inferred, and nothing is writable
through the UI.
"""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.registry.models import Aircraft, Battery


def _client(*codenames, member_of=None):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    if member_of is not None:
        member_of.members.add(user)
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


class TestSerialIsTheJoinKey:
    """The whole point of the model: AeroLink resolves a battery by the serial
    DJI reports, so that value has to behave exactly like
    Aircraft.serial_number (X.1)."""

    @pytest.mark.django_db
    def test_whitespace_is_normalized_on_save(self):
        battery = Battery.objects.create(serial_number=" 3YM 8K12 3456 ")

        battery.refresh_from_db()
        assert battery.serial_number == "3YM8K123456"

    @pytest.mark.django_db
    def test_a_hand_typed_serial_matches_the_telemetry_form(self):
        """A human typing spaces and AeroLink sending none must collide, not
        create a second row for the same physical battery."""
        Battery.objects.create(serial_number="3YM8K123456")

        with pytest.raises(IntegrityError):
            Battery.objects.create(serial_number="3YM 8K12 3456")

    @pytest.mark.django_db
    def test_a_blank_serial_is_refused(self):
        """Unlike Aircraft (where a missing serial is a legitimate NULL), a
        battery with no serial cannot be joined to anything, so it is useless
        as evidence."""
        with pytest.raises(ValidationError):
            Battery(serial_number="   ").full_clean()


class TestProvenance:
    @pytest.mark.django_db
    def test_defaults_to_manual_and_never_synced(self):
        battery = Battery.objects.create(serial_number="ABC123")

        assert battery.source == Battery.SOURCE_MANUAL
        assert battery.synced_at is None

    @pytest.mark.django_db
    def test_the_list_distinguishes_synced_from_never_synced(self):
        """A cycle count with no sync date is ambiguous -- new battery, or a
        sync that never ran? The list has to say which."""
        never = Battery.objects.create(serial_number="NEVERSYNCED", cycle_count=0)
        synced_at = timezone.now()
        Battery.objects.create(
            serial_number="FRESH",
            cycle_count=42,
            source=Battery.SOURCE_AEROLINK,
            synced_at=synced_at,
        )

        content = _client("view_battery").get(reverse("battery-list")).content.decode()

        assert "NEVERSYNCED" in content
        assert "FRESH" in content
        # The synced row shows its timestamp; the never-synced one falls back to
        # its source label. Compared against what Django itself renders, so the
        # assertion does not depend on the translation being in place.
        assert synced_at.strftime("%Y-%m-%d") in content
        assert str(never.get_source_display()) in content


class TestHealthConstraint:
    @pytest.mark.django_db
    def test_health_above_100_is_refused_by_the_database(self):
        """A percentage over 100 means a bad sync, not a very healthy battery --
        the constraint is the real guard, so it is tested by bypassing clean()."""
        with pytest.raises(IntegrityError):
            Battery.objects.create(serial_number="BADHEALTH", health_percent=140)

    @pytest.mark.django_db
    def test_null_health_is_allowed(self):
        """Not yet reported is a legitimate state; it must not be conflated
        with 0% (a dead battery)."""
        battery = Battery.objects.create(serial_number="UNKNOWNHEALTH")
        assert battery.health_percent is None


class TestListSurface:
    @pytest.mark.django_db
    def test_requires_view_battery_permission(self):
        assert _client().get(reverse("battery-list")).status_code == 403
        assert _client("view_battery").get(reverse("battery-list")).status_code == 200

    @pytest.mark.django_db
    def test_empty_state_explains_why_it_is_empty(self):
        """Until X.4 exists this list is empty; a bare "no records" would read
        as a bug rather than the designed state."""
        response = _client("view_battery").get(reverse("battery-list"))

        content = response.content.decode()
        assert "AeroLink" in content

    @pytest.mark.django_db
    def test_no_create_edit_or_archive_routes_exist(self):
        """ADR-0002: AeroLink is the master, so there is no write surface to
        gate -- the URLs are simply not registered."""
        from django.urls import NoReverseMatch

        for name in (
            "battery-create",
            "battery-update",
            "battery-archive",
            "battery-detail",
        ):
            with pytest.raises(NoReverseMatch):
                reverse(name)

    @pytest.mark.django_db
    def test_list_offers_no_new_button(self):
        Battery.objects.create(serial_number="ABC123")

        content = _client("view_battery").get(reverse("battery-list")).content.decode()

        assert "+ Nuevo" not in content
        assert "+ New" not in content

    @pytest.mark.django_db
    def test_shows_the_aircraft_it_was_last_seen_on(self):
        aircraft = Aircraft.objects.create(
            registration="RPA-4401", type="Multirotor", model="M3E", manufacturer="DJI"
        )
        Battery.objects.create(serial_number="ABC123", aircraft=aircraft)

        content = _client("view_battery").get(reverse("battery-list")).content.decode()

        assert "RPA-4401" in content

    @pytest.mark.django_db
    def test_search_matches_serial_and_model(self):
        Battery.objects.create(serial_number="AAA111", model="TB65")
        Battery.objects.create(serial_number="BBB222", model="BS60")

        client = _client("view_battery")
        by_serial = client.get(reverse("battery-list"), {"q": "AAA"}).content.decode()
        assert "AAA111" in by_serial
        assert "BBB222" not in by_serial

        by_model = client.get(reverse("battery-list"), {"q": "BS60"}).content.decode()
        assert "BBB222" in by_model
        assert "AAA111" not in by_model

    @pytest.mark.django_db
    def test_csv_export_works(self):
        Battery.objects.create(serial_number="ABC123", cycle_count=17)

        response = _client("view_battery").get(
            reverse("battery-list"), {"export": "csv"}
        )

        assert response.status_code == 200
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        assert "ABC123" in body


class TestTenantScoping:
    @pytest.mark.django_db
    def test_another_tenants_battery_does_not_leak(self):
        other = OperationalTenant.objects.create(name="Otro", slug="otro")
        Battery.objects.create(serial_number="MINE", cycle_count=1)
        Battery.objects.create(serial_number="THEIRS", cycle_count=2, tenant=other)

        content = _client("view_battery").get(reverse("battery-list")).content.decode()

        assert "MINE" in content
        assert "THEIRS" not in content

    @pytest.mark.django_db
    def test_scoping_filters_both_ways(self):
        other = OperationalTenant.objects.create(name="Otro", slug="otro")
        Battery.objects.create(serial_number="MINE", cycle_count=1)
        Battery.objects.create(serial_number="THEIRS", cycle_count=2, tenant=other)

        content = (
            _client("view_battery", member_of=other)
            .get(reverse("battery-list"))
            .content.decode()
        )

        assert "THEIRS" in content
        assert "MINE" not in content
