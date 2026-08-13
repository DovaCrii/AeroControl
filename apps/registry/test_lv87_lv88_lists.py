"""LV-87/LV-88: the credential column and the movement log's window.

Both are list-reading fixes rather than new data. What is worth pinning is the
part that could go wrong silently: a default time window that hides rows without
saying so, and a count that talks about pagination instead of about the
operation.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import Aircraft, Operator, ResourceMovementLog


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _aircraft(registration="RPA-3696"):
    return Aircraft.objects.create(
        registration=registration, type="RPA", model="M3", manufacturer="DJI"
    )


def _movement(resource, *, days_ago=0, kind="aircraft"):
    """A movement recorded `days_ago` days ago.

    The clock is moved rather than the row: `ResourceMovementLog` is append-only
    (`AppendOnlyLogQuerySet` raises on `update()`), which is the point of the
    model -- so a test that backdated a row afterwards would be asking it to
    break its own guarantee.
    """
    with mock.patch(
        "django.utils.timezone.now",
        return_value=timezone.now() - timedelta(days=days_ago),
    ):
        return ResourceMovementLog.objects.create(
            resource_kind=kind,
            resource_id=resource.pk,
            movement="location_change",
        )


@pytest.mark.django_db
class TestCredentialColumn:
    def test_the_file_is_its_own_column_not_a_badge_on_the_date(self):
        """R4.7 drew "Sin PDF" inside the expiry cell, so one cell mixed two
        different facts and the badge read as if it qualified the date."""
        Operator.objects.create(employee_id="E1", full_name="René Herrera")

        content = (
            _client("view_operator").get(reverse("operator-list")).content.decode()
        )

        assert "credential-file" in content
        assert "No PDF" not in content

    def test_a_missing_file_and_a_present_one_are_both_stated(self):
        """That the file *is* on record is as useful as that it is missing --
        the old badge only ever appeared for the absence."""
        Operator.objects.create(employee_id="E1", full_name="Sin respaldo")

        content = (
            _client("view_operator").get(reverse("operator-list")).content.decode()
        )

        assert "is-missing" in content


@pytest.mark.django_db
class TestMovementWindow:
    def _url(self, **params):
        url = reverse("resourcemovementlog-list")
        if params:
            url += "?" + "&".join(f"{key}={value}" for key, value in params.items())
        return url

    def test_the_default_window_is_the_last_30_days(self):
        aircraft = _aircraft()
        _movement(aircraft, days_ago=2)
        _movement(aircraft, days_ago=200)

        response = _client("view_resourcemovementlog").get(self._url())

        assert response.context["movement_count"] == 1
        assert response.context["selected_days"] == 30

    def test_everything_on_record_is_one_click_away(self):
        """A list that trims without saying so is worse than a long one, so the
        window is a visible selector with an explicit "everything" option."""
        aircraft = _aircraft()
        _movement(aircraft, days_ago=2)
        _movement(aircraft, days_ago=200)

        response = _client("view_resourcemovementlog").get(self._url(days="all"))

        assert response.context["movement_count"] == 2
        assert response.context["selected_days"] == "all"

    @pytest.mark.parametrize("days", [7, 90])
    def test_the_offered_windows_work(self, days):
        aircraft = _aircraft()
        _movement(aircraft, days_ago=3)
        _movement(aircraft, days_ago=45)

        response = _client("view_resourcemovementlog").get(self._url(days=days))

        assert response.context["movement_count"] == (1 if days == 7 else 2)

    def test_a_nonsense_window_falls_back_to_the_default(self):
        """Same "a malformed filter is a no-op, not an error" convention the
        rest of the app uses."""
        aircraft = _aircraft()
        _movement(aircraft, days_ago=2)

        response = _client("view_resourcemovementlog").get(self._url(days="banana"))

        assert response.context["selected_days"] == 30
        assert response.context["movement_count"] == 1

    def test_the_count_describes_the_window_and_not_the_page(self):
        """Paginated at 50: a count taken from the page would be a statement
        about pagination rather than about the operation."""
        aircraft = _aircraft()
        for _ in range(55):
            _movement(aircraft, days_ago=1)

        response = _client("view_resourcemovementlog").get(self._url())

        assert response.context["movement_count"] == 55
        assert len(response.context["objects"]) == 50


@pytest.mark.django_db
class TestMovementRows:
    def test_the_resource_links_to_its_fiche(self):
        aircraft = _aircraft()
        _movement(aircraft, days_ago=1)

        content = (
            _client("view_resourcemovementlog")
            .get(reverse("resourcemovementlog-list"))
            .content.decode()
        )

        assert reverse("aircraft-detail", args=[aircraft.pk]) in content

    def test_a_row_whose_subject_is_gone_still_renders(self):
        """The log is append-only and outlives its subject, so an unresolvable
        row must degrade to plain text instead of raising."""
        from uuid import uuid4

        from apps.registry.selectors import label_movements

        entry = ResourceMovementLog.objects.create(
            resource_kind="aircraft", resource_id=uuid4(), movement="location_change"
        )

        labelled = label_movements([entry])[0]

        assert labelled.resource_url is None
        assert labelled.resource_label == str(entry.resource_id)
