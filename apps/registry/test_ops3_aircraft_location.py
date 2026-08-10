"""OPS-3: physical aircraft location, its validation, and the movement log."""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.registry.models import Aircraft, CostCenter, ResourceMovementLog


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "CC-AAA"),
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


class TestValidation:
    @pytest.mark.django_db
    def test_defaults_to_headquarters_with_no_site(self, db):
        aircraft = _aircraft()
        assert aircraft.current_location == "headquarters"
        assert aircraft.current_site_id is None
        aircraft.full_clean()  # must not raise

    @pytest.mark.django_db
    def test_on_site_requires_a_site(self, db):
        aircraft = _aircraft(current_location="on_site")
        with pytest.raises(ValidationError):
            aircraft.full_clean()

    @pytest.mark.django_db
    def test_non_on_site_rejects_a_site(self, db):
        cc = CostCenter.objects.create(code="CC1", name="CC1")
        aircraft = _aircraft(current_location="maintenance", current_site=cc)
        with pytest.raises(ValidationError):
            aircraft.full_clean()

    @pytest.mark.django_db
    def test_on_site_with_a_site_passes(self, db):
        cc = CostCenter.objects.create(code="CC1", name="CC1")
        aircraft = _aircraft(current_location="on_site", current_site=cc)
        aircraft.full_clean()  # must not raise


class TestMovementLog:
    @pytest.mark.django_db
    def test_creating_an_aircraft_logs_nothing(self, db):
        _aircraft()
        assert not ResourceMovementLog.objects.filter(
            movement="location_changed"
        ).exists()

    @pytest.mark.django_db
    def test_moving_to_a_site_logs_location_changed(self, db):
        aircraft = _aircraft()
        cc = CostCenter.objects.create(code="CC1", name="Site One")
        aircraft.current_location = "on_site"
        aircraft.current_site = cc
        aircraft.save(update_fields=["current_location", "current_site", "updated_at"])

        log = ResourceMovementLog.objects.get(
            resource_kind="aircraft", resource_id=aircraft.pk
        )
        assert log.movement == "location_changed"
        assert log.from_cost_center_id is None
        assert log.to_cost_center_id == cc.pk
        # get_FOO_display() renders in the active language; LANGUAGE_CODE is
        # "es" project-wide (config/settings/base.py), so the detail text is
        # Spanish, matching every other rendered-text assertion in this suite.
        assert "Casa matriz" in log.detail
        assert "En faena" in log.detail

    @pytest.mark.django_db
    def test_moving_between_sites_logs_from_and_to(self, db):
        cc1 = CostCenter.objects.create(code="CC1", name="Site One")
        cc2 = CostCenter.objects.create(code="CC2", name="Site Two")
        aircraft = _aircraft(current_location="on_site", current_site=cc1)

        aircraft.current_site = cc2
        aircraft.save(update_fields=["current_site", "updated_at"])

        log = ResourceMovementLog.objects.filter(
            resource_kind="aircraft", resource_id=aircraft.pk
        ).latest("sequence")
        assert log.movement == "location_changed"
        assert log.from_cost_center_id == cc1.pk
        assert log.to_cost_center_id == cc2.pk

    @pytest.mark.django_db
    def test_returning_to_maintenance_clears_site_reference(self, db):
        cc = CostCenter.objects.create(code="CC1", name="Site One")
        aircraft = _aircraft(current_location="on_site", current_site=cc)

        aircraft.current_location = "maintenance"
        aircraft.current_site = None
        aircraft.save(update_fields=["current_location", "current_site", "updated_at"])

        log = ResourceMovementLog.objects.filter(
            resource_kind="aircraft", resource_id=aircraft.pk
        ).latest("sequence")
        assert log.from_cost_center_id == cc.pk
        assert log.to_cost_center_id is None

    @pytest.mark.django_db
    def test_no_change_logs_nothing_extra(self, db):
        aircraft = _aircraft()
        aircraft.save()  # resave with identical field values
        assert not ResourceMovementLog.objects.filter(
            resource_id=aircraft.pk, movement="location_changed"
        ).exists()

    @pytest.mark.django_db
    def test_editing_location_via_the_view_attributes_the_user(self, db):
        """R5.2 [bug]: editing an aircraft's location through the ordinary
        form used to log a movement with no author -- RegistryUpdate did not
        set `_changed_by_user` before saving."""
        aircraft = _aircraft()
        cc = CostCenter.objects.create(code="CC1", name="Site One")
        client = _client("change_aircraft")
        user = User.objects.get(username="u-change_aircraft")

        client.post(
            reverse("aircraft-update", args=[aircraft.pk]),
            {
                "registration": aircraft.registration,
                "type": aircraft.type,
                "model": aircraft.model,
                "manufacturer": aircraft.manufacturer,
                "current_location": "on_site",
                "current_site": cc.pk,
                "status": "active",
            },
        )

        log = ResourceMovementLog.objects.get(
            resource_kind="aircraft", resource_id=aircraft.pk
        )
        assert log.changed_by_user_id == user.pk


class TestListRendersLocationBadge:
    @pytest.mark.django_db
    def test_aircraft_list_shows_location_column(self, db):
        cc = CostCenter.objects.create(code="CC1", name="Site One")
        _aircraft(registration="CC-HQ")
        _aircraft(registration="CC-SITE", current_location="on_site", current_site=cc)

        response = _client("view_aircraft").get(reverse("aircraft-list"))

        content = response.content.decode()
        assert response.status_code == 200
        # Rendered in Spanish (LANGUAGE_CODE = "es"), same reasoning as above.
        assert "Casa matriz" in content
        assert "En faena" in content
        assert "Site One" in content
